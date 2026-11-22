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
    if 'availability-windows' in outputs:
        segments = outputs['availability-windows']['segments']
        assert segments[0]['from'] == '2026-10-30' and segments[-1]['until'] == '2027-01-02'
        assert all(left['until'] == right['from'] for left, right in zip(segments, segments[1:]))
        assert 'D' in segments[0]['status']['certified'] and 'D' in segments[1]['status']['unusable']
        assert 'A' in segments[-1]['status']['unusable']
    if 'witness' in outputs:
        report = outputs['witness']
        assert [r['state'] for r in report['rows']] == ['consistent', 'consistent', 'disjoint', 'unresolved_certificate']
        assert all(r['measured_in_target'] for r in report['rows']) and not report['accepted']



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
    call('/api/replay', {'run': '0' * 64}, fault=(404, 'run_not_found'))
    call('/api/compare', {'dataset': 'unrelated', 'before': first['id'], 'after': second['id'], 'operation': selected[0]},
         fault=(409, 'revision_wrong_dataset'))
    bundle = call(f"/api/evidence/{original_run['id']}")
    assert bundle['raw'] == document and bundle['raw_sha'] == sha256(document.encode()).hexdigest()
    assert bundle['document_sha'] == first['document_sha'] and bundle['result'] == original_run
    assert bundle['publication']['generation'] == 1
    call('/api/evidence/' + '0' * 64, fault=(404, 'run_not_found'))
    # Modify only this disposable example store to exercise legacy engine and digest rejection.
    with sqlite3.connect(db_path) as db:
        db.execute('UPDATE runs SET engine=?, output_sha=? WHERE id=?', ('retired-engine', '0' * 64, original_run['id']))
    call('/api/replay', {'run': original_run['id']}, fault=(409, 'engine_version_unavailable'))
    call('/api/evidence/' + original_run['id'], fault=(409, 'evidence_digest_mismatch'))
    with sqlite3.connect(db_path) as db:
        db.execute('UPDATE runs SET engine=?, output_sha=? WHERE id=?',
                   (original_run['engine'], original_run['output_sha'], original_run['id']))
    assert call('/api/evidence/' + original_run['id']) == bundle

    restore = {'dataset': name, 'revision': first['id'], 'generation': 2}
    call('/api/restore', {**restore, 'dataset': 'unrelated'}, fault=(409, 'revision_wrong_dataset'))
    call('/api/restore', {**restore, 'generation': 1}, fault=(409, 'generation_conflict'))
    assert call('/api/restore', restore) == {'generation': 3, 'revision': first['id']}
    assert call('/api/run', {'dataset': name, 'operations': selected}) == produced
    assert call('/api/publish', {'draft': second['id']})['reused']
    if 'witness' in selected:
        run = next(row for row in produced['runs'] if row['operation'] == 'witness')
        call('/api/review/open', {'run': run['id'], 'generation': 1}, fault=(409, 'review_activation_changed'))
        start = {'run': run['id'], 'generation': 3}
        bad = call('/api/review/open', start)
        assert bad['state'] == 'open' and bad['eligible'] == 0
        assert call('/api/review/open', start) == bad
        request = {'review': bad['id']}
        call('/api/dispatch', request, fault=(409, 'dispatch_requires_approval'))
        call('/api/review/decide', {**request, 'decision': 'approved'}, fault=(409, 'review_domain_not_eligible'))
        assert call('/api/review/decide', {**request, 'decision': 'returned'})['state'] == 'returned'
        call('/api/review/decide', {**request, 'decision': 'approved'}, fault=(409, 'review_already_decided'))
        doc = json.loads(document)
        doc['witness_readings'] = doc['witness_readings'][:1]
        probe_name = name + '-probe'

        def install(source):
            draft = call('/api/stage', {'dataset': probe_name, 'source': source, 'text': json.dumps(doc)})
            assert draft['state'] == 'ready'
            call('/api/publish', {'draft': draft['id']})
            return draft['id']

        good_revision = install('verified.json')
        qualified = call('/api/run', {'dataset': probe_name, 'operations': ['witness']})['runs'][0]
        output = qualified['output']
        assert output['accepted'], output
        initial = {'run': qualified['id'], 'generation': 1}
        case = call('/api/review/open', initial)
        assert case['eligible'] == 1
        request = {'review': case['id']}
        attachment = '/api/dispatch/' + case['id']
        call(attachment, fault=(404, 'dispatch_not_found'))
        approved = call('/api/review/decide', {**request, 'decision': 'approved'})
        assert approved['state'] == 'approved'
        assert call('/api/review/decide', {**request, 'decision': 'approved'}) == approved
        receipt = call('/api/dispatch', request)
        package = call(attachment)
        assert package['receipt'] == receipt and package['payload']['evidence']['result'] == qualified
        assert sha256(json.dumps(package['payload'], ensure_ascii=True, sort_keys=True,
                                 separators=(',', ':')).encode()).hexdigest() == receipt['payload_sha']
        assert call('/api/review/history', {'run': qualified['id']})['cases'][0]['dispatched']
        del doc['witness_readings']
        incomplete = install('without-optional-evidence.json')
        call('/api/run', {'dataset': probe_name, 'operations': [selected[0], 'witness']}, fault=(422, 'domain_input'))
        with sqlite3.connect(db_path) as db:
            assert db.execute('SELECT count(*) FROM runs WHERE revision=?', (incomplete,)).fetchone()[0] == 0
        prior = call('/api/run', {'dataset': probe_name, 'revision': good_revision, 'operations': ['witness']})['runs'][0]
        assert call(attachment) == package
        assert call('/api/dispatch', request) == receipt
        call('/api/restore', {'dataset': probe_name, 'revision': good_revision, 'generation': 2})
        fresh_case = call('/api/review/open', {**initial, 'generation': 3})
        assert fresh_case['id'] != case['id'] and fresh_case['state'] == 'open'
        fresh_request = {'review': fresh_case['id']}
        call('/api/dispatch', fresh_request, fault=(409, 'dispatch_requires_approval'))
        assert call('/api/review/decide', {**fresh_request, 'decision': 'approved'})['state'] == 'approved'
        install('next-batch.json')
        call('/api/dispatch', fresh_request, fault=(409, 'review_activation_changed'))
        call('/api/dispatch/' + fresh_case['id'], fault=(404, 'dispatch_not_found'))
        assert call(attachment) == package
        assert prior['output'] == output and call('/api/replay', {'run': prior['id']})['matches']

    history = call('/api/history', {'dataset': name})
    assert [row['action'] for row in history['events']] == ['restore', 'publish', 'publish']
    assert history['head'] == {'generation': 3, 'revision': first['id']}
    import downstream_case
    import expansion_case
    import specialty_case

    for case in (expansion_case, downstream_case, specialty_case):
        if case.OPERATION in selected:
            exercise_expansion(call, db_path, name + "-" + case.OPERATION, document, case)



def exercise_expansion(call, db_path, name, document, case):
    operation = case.OPERATION

    def install(source, doc):
        text = json.dumps(doc, ensure_ascii=False)
        record = call('/api/stage', {'dataset': name, 'source': source, 'text': text})
        assert record['state'] == 'ready'
        call('/api/publish', {'draft': record['id']})
        return record['id'], text

    doc = json.loads(document)
    plain = json.loads(document)
    del plain[case.OPTIONAL_FIELD]
    old, _ = install('old-style.json', plain)
    params = {'dataset': name, 'operations': [profile.REQUIRED[0], operation]}
    call('/api/run', params, fault=(422, 'domain_input'))
    with sqlite3.connect(db_path) as db:
        assert db.execute('SELECT count(*) FROM runs WHERE revision=?', (old,)).fetchone()[0] == 0
    legacy = call('/api/run', {**params, 'operations': [profile.REQUIRED[0]]})['runs'][0]

    a, raw = install('first-qualification.json', doc)
    first = call('/api/run', params)['runs']
    assert first[0]['output'] == legacy['output']
    if hasattr(case, 'edge_cases'):
        case.edge_cases(doc)
    case.perturb(doc)
    b, _ = install('changed-evidence.json', doc)
    second = call('/api/run', params)['runs']
    pinned = first[1]
    case.verify(pinned['output'], second[1]['output'])
    assert call('/api/run', {**params, 'revision': a})['runs'] == first
    comparison = call('/api/compare', {'dataset': name, 'before': a, 'after': b, 'operation': operation})
    assert comparison['output_changed']
    assert comparison['before_output'] == pinned['output'] and comparison['after_output'] == second[1]['output']
    replay = call('/api/replay', {'run': pinned['id']})
    assert replay['matches'] and replay['revision'] == a
    bundle = call('/api/evidence/' + pinned['id'])
    assert bundle['raw'] == raw and bundle['result'] == pinned and bundle['publication']['generation'] == 2


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
