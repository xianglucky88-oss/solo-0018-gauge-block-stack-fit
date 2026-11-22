"""Exercise the actual local HTTP service and SQLite transaction boundaries."""
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench import profile
from workbench.db import initialize
from workbench.http import Endpoint
from workbench.service import Service


class QuietEndpoint(Endpoint):
    def log_message(self, *args):
        pass


def domain_checks(outputs):
    if 'quotation' in outputs:
        match, = outputs['quotation']['matches']
        assert [source['ref'] for source in match['sources']] == ['n-title', 'n-right']
        assert match['separator_characters'] == 1
    if 'composite' in outputs:
        row, = outputs['composite']['rows']
        assert row['mass'] == {'dry_g': 300, 'retained_g': [170, 80], 'pan_g': 50}
    if 'interval-accounts' in outputs:
        summary = outputs['interval-accounts']
        assert summary['whole_dose'] == outputs['dose']['dose']
        assert sum(row['unknown_seconds'] for row in summary['segments']) == 15
    if 'year-proof' in outputs:
        proof, dated = outputs['year-proof'], outputs['dated-widths']
        assert proof['state'] == dated['state'] == 'dated'
        assert [row['year'] for row in proof['years']] == [row['year'] for row in dated['dated_widths']]
        assert all(row['used_for_alignment'] == (row['comparison'] is not None) for row in proof['years'])
    if 'availability-windows' in outputs:
        segments = outputs['availability-windows']['segments']
        assert segments[0]['from'] == '2026-10-30' and segments[-1]['until'] == '2027-01-02'
        assert all(left['until'] == right['from'] for left, right in zip(segments, segments[1:]))
        assert 'D' in segments[0]['status']['certified'] and 'D' in segments[1]['status']['unusable']
        assert 'A' in segments[-1]['status']['unusable']


def exercise(port, db_path, operation):
    def call(route, data=None, *, fault=None):
        kwargs = {} if data is None else {'data': json.dumps(data).encode(),
                                         'headers': {'Content-Type': 'application/json'}}
        request = Request(f'http://127.0.0.1:{port}{route}', **kwargs)
        try:
            with urlopen(request, timeout=10) as response:
                assert fault is None, (route, fault)
                body = response.read()
                return json.loads(body) if response.headers.get_content_type() == 'application/json' else body
        except HTTPError as exc:
            with exc:
                assert (exc.code, json.load(exc)['error']) == fault, (route, exc.code, fault)

    name = profile.DEFAULT_DATASET
    document = (ROOT / 'examples/workbench.json').read_bytes().decode('utf-8')
    names = list(profile.OPERATIONS)
    selected = list(dict.fromkeys([*profile.REQUIRED, operation])) if operation else names
    assert b'type="module"' in call('/')
    assert b'fetch(' in call('/assets/api.js')
    assert call('/example.json') == json.loads(document)
    assert list(op['id'] for op in call('/api/meta')['operations']) == names

    def stage(source, text=document):
        return call('/api/stage', {'dataset': name, 'source': source, 'text': text})

    assert call('/api/history', {'dataset': name})['head'] == {'generation': 0, 'revision': None}
    rejected = stage('empty.json', '{}')
    assert rejected['state'] == 'rejected'
    call('/api/publish', {'draft': rejected['id']}, fault=(409, 'draft_rejected'))
    first, stale = stage('original.json'), stage('concurrent.json')
    assert first['state'] == stale['state'] == 'ready'
    assert stage('original.json') == first
    assert call('/api/publish', {'draft': first['id']})['head']['generation'] == 1
    call('/api/publish', {'draft': stale['id']}, fault=(409, 'generation_conflict'))

    produced = call('/api/run', {'dataset': name, 'operations': selected})
    assert produced['revision'] == first['id']
    assert len(produced['runs']) == len(selected)
    assert all(row['revision'] == first['id'] for row in produced['runs'])
    domain_checks({row['operation']: row['output'] for row in produced['runs']})
    original_run = produced['runs'][0]

    changed = json.dumps({**json.loads(document), 'audit_note': 'second delivery'}, ensure_ascii=False)
    second = stage('revised.json', changed)
    assert call('/api/publish', {'draft': second['id']})['head']['generation'] == 2
    base = {'dataset': name, 'operations': [selected[0], 'does-not-exist']}
    call('/api/run', base, fault=(404, 'unknown_operation'))
    with sqlite3.connect(db_path) as db:
        assert db.execute('SELECT count(*) FROM runs WHERE revision=?', (second['id'],)).fetchone()[0] == 0
        assert not db.execute('SELECT 1 FROM versions WHERE id=?', (stale['id'],)).fetchone()
    assert call('/api/run', {**base, 'operations': selected})['revision'] == second['id']
    assert call('/api/run', {**base, 'operations': selected, 'revision': first['id']}) == produced
    comparison = call('/api/compare', {'dataset': name, 'before': first['id'], 'after': second['id'], 'operation': selected[0]})
    assert comparison['input_changes'] == [{'field': 'audit_note', 'change': 'added'}]
    assert not comparison['output_changed']
    replay = call('/api/replay', {'run': original_run['id']})
    assert replay['matches'] and replay['revision'] == first['id']
    bundle = call(f"/api/evidence/{original_run['id']}")
    assert bundle['raw'] == document and bundle['raw_sha'] == sha256(document.encode()).hexdigest()
    assert bundle['document_sha'] == first['document_sha'] and bundle['result'] == original_run
    assert bundle['publication']['generation'] == 1

    restore = {'dataset': name, 'revision': first['id'], 'generation': 2}
    call('/api/restore', {**restore, 'dataset': 'unrelated'}, fault=(409, 'revision_wrong_dataset'))
    call('/api/restore', {**restore, 'generation': 1}, fault=(409, 'generation_conflict'))
    assert call('/api/restore', restore) == {'generation': 3, 'revision': first['id']}
    assert call('/api/run', {'dataset': name, 'operations': selected}) == produced
    assert call('/api/publish', {'draft': second['id']})['reused']
    history = call('/api/history', {'dataset': name})
    assert [row['action'] for row in history['events']] == ['restore', 'publish', 'publish']
    assert history['head'] == {'generation': 3, 'revision': first['id']}


def main():
    operation = sys.argv[1] if len(sys.argv) == 2 else None
    if len(sys.argv) > 2 or (operation is not None and operation not in profile.OPERATIONS):
        raise SystemExit('usage: python3 -B examples/workbench_check.py [operation]')
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / 'test.sqlite3'
        initialize(db, profile.PRODUCT)
        with ThreadingHTTPServer(('127.0.0.1', 0), QuietEndpoint) as server:
            server.service = Service(db, profile)
            worker = Thread(target=server.serve_forever)
            worker.start()
            try:
                exercise(server.server_port, db, operation)
            finally:
                server.shutdown()
                worker.join()
    print(f'{profile.PRODUCT}: HTTP, SQLite and domain checks passed')


if __name__ == '__main__':
    main()
