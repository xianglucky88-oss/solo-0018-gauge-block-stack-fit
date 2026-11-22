from .catalog import head, resolve
from .codec import generation, identifier
from .errors import Problem


def _activate(db, name, revision, expected, action):
    generation(expected)
    current = head(db, name)
    if current['generation'] != expected:
        raise Problem('generation_conflict', 409)
    if current['revision'] == revision:
        return current
    next_generation = expected + 1
    db.execute('''INSERT INTO heads VALUES(?, ?, ?) ON CONFLICT(dataset) DO UPDATE
                  SET generation=excluded.generation, revision=excluded.revision''', (name, next_generation, revision))
    db.execute('INSERT INTO publication_events(dataset, generation, revision, action) VALUES(?, ?, ?, ?)',
               (name, next_generation, revision, action))
    return {'generation': next_generation, 'revision': revision}


def publish(db, draft_id):
    row = db.execute('SELECT * FROM drafts WHERE id=?', (identifier(draft_id),)).fetchone()
    if row is None:
        raise Problem('draft_not_found', 404)
    if row['state'] == 'rejected':
        raise Problem('draft_rejected', 409)
    if row['state'] == 'published':
        return {'dataset': row['dataset'], 'revision': row['id'], 'head': head(db, row['dataset']), 'reused': True}
    db.execute('INSERT INTO versions(id, dataset, document, document_sha) VALUES(?, ?, ?, ?)',
               (row['id'], row['dataset'], row['document'], row['document_sha']))
    now = _activate(db, row['dataset'], row['id'], row['base'], 'publish')
    db.execute("UPDATE drafts SET state='published' WHERE id=?", (row['id'],))
    return {'dataset': row['dataset'], 'revision': row['id'], 'head': now, 'reused': False}


def restore(db, name, revision, expected):
    identifier(revision)
    row = resolve(db, name, revision)
    return _activate(db, name, row['id'], expected, 'restore')
