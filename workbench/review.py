"""Review a domain result against one activation, without altering its input."""
from . import catalog, evidence, runs
from .codec import encode, generation, identifier, sha
from .errors import Problem


def get(db, review_id):
    row = db.execute('SELECT * FROM reviews WHERE id=?', (identifier(review_id),)).fetchone()
    if row is None:
        raise Problem('review_not_found', 404)
    return dict(row)


def _current(db, name, activation, revision):
    if catalog.head(db, name) != {'generation': activation, 'revision': revision}:
        raise Problem('review_activation_changed', 409)


def open_case(db, policy, run_id, activation):
    generation(activation)
    run = runs.fetch(db, run_id)
    operation, eligible = policy
    if run['operation'] != operation:
        raise Problem('review_operation', 409)
    bundle = evidence.export(db, run_id)
    name, revision = bundle['dataset'], run['revision']
    _current(db, name, activation, revision)
    key = sha(encode([run_id, activation]))
    db.execute('''INSERT INTO reviews(id,dataset,generation,run,eligible) VALUES (?,?,?,?,?)
                  ON CONFLICT(id) DO NOTHING''', (key, name, activation, run_id, eligible(bundle['result']['output'])))
    return get(db, key)


def decide(db, review_id, decision):
    case = get(db, review_id)
    if decision not in ('approved', 'returned'):
        raise Problem('review_decision')
    if case['state'] == decision:
        return case
    if case['state'] != 'open':
        raise Problem('review_already_decided', 409)
    if decision == 'approved':
        run = runs.fetch(db, case['run'])
        _current(db, case['dataset'], case['generation'], run['revision'])
        if not case['eligible']:
            raise Problem('review_domain_not_eligible', 409)
    db.execute('UPDATE reviews SET state=? WHERE id=?', (decision, review_id))
    return get(db, review_id)


def for_run(db, run_id):
    runs.fetch(db, run_id)
    return [dict(row) for row in db.execute('''SELECT r.*, d.review IS NOT NULL AS dispatched
        FROM reviews r LEFT JOIN dispatches d ON r.id=d.review WHERE r.run=? ORDER BY r.generation DESC''',
        (run_id,))]
