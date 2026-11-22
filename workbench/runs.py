from .catalog import resolve, version
from .codec import decode, encode, identifier, sha
from .errors import Problem

ENGINE = 'workbench-1'


def fetch(db, run_id):
    row = db.execute('SELECT * FROM runs WHERE id=?', (identifier(run_id),)).fetchone()
    if row is None:
        raise Problem('run_not_found', 404)
    return row


def result(row):
    return {**dict(row), 'output': decode(row['output'])}


def materialize(db, ops, row, name):
    if not isinstance(name, str) or name not in ops.operations:
        raise Problem('unknown_operation', 404)
    key = sha(encode([row['id'], name, ENGINE]))
    cached = db.execute('SELECT * FROM runs WHERE id=?', (key,)).fetchone()
    if cached:
        return result(cached)
    output = ops.run(name, row['document'])
    db.execute('INSERT INTO runs(id, revision, operation, engine, output, output_sha) VALUES(?, ?, ?, ?, ?, ?)',
               (key, row['id'], name, ENGINE, output, sha(output)))
    return result(fetch(db, key))


def batch(db, ops, dataset, revision, names):
    if not isinstance(names, list) or not 1 <= len(names) <= len(ops.operations):
        raise Problem('operation_selection')
    if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
        raise Problem('operation_selection')
    pinned = resolve(db, dataset, revision)
    return {'revision': pinned['id'], 'runs': [materialize(db, ops, pinned, name) for name in names]}


def replay(db, ops, run_id):
    row = fetch(db, run_id)
    if row['engine'] != ENGINE:
        raise Problem('engine_version_unavailable', 409)
    pinned = version(db, row['revision'])
    output = ops.run(row['operation'], pinned['document'])
    return {'run': row['id'], 'revision': pinned['id'], 'expected_sha': row['output_sha'],
            'actual_sha': sha(output), 'matches': output == row['output'] and sha(output) == row['output_sha']}
