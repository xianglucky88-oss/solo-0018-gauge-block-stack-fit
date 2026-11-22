from .codec import dataset, identifier
from .errors import Problem


def head(db, name):
    dataset(name)
    row = db.execute('SELECT generation, revision FROM heads WHERE dataset=?', (name,)).fetchone()
    return dict(row) if row else {'generation': 0, 'revision': None}


def version(db, revision):
    row = db.execute('SELECT * FROM versions WHERE id=?', (identifier(revision),)).fetchone()
    if row is None:
        raise Problem('revision_not_found', 404)
    return row


def resolve(db, name, revision=None):
    current = head(db, name)
    if revision is None:
        revision = current['revision']
    if revision is None:
        raise Problem('no_published_revision', 409)
    row = version(db, revision)
    if row['dataset'] != name:
        raise Problem('revision_wrong_dataset', 409)
    return row


def listing(db):
    return [dict(row) for row in db.execute('SELECT * FROM heads ORDER BY dataset LIMIT 100')]
