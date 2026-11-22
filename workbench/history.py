from .catalog import head


def for_dataset(db, name):
    current = head(db, name)
    versions = db.execute('''
        SELECT v.id, v.created, v.document_sha, d.source
        FROM versions v JOIN drafts d ON d.id=v.id
        JOIN publication_events p ON p.revision=v.id AND p.action='publish'
        WHERE v.dataset=?
        ORDER BY (v.id=?) DESC, p.generation DESC LIMIT 100
    ''', (name, current['revision']))
    events = db.execute('''
        SELECT generation, revision, action, created FROM publication_events
        WHERE dataset=? ORDER BY generation DESC LIMIT 100
    ''', (name,))
    drafts = db.execute('''
        SELECT id, base, source, state, reason, created FROM drafts
        WHERE dataset=? AND state!='published' ORDER BY created DESC, id LIMIT 50
    ''', (name,))
    return {'dataset': name, 'head': current, 'versions': list(map(dict, versions)),
            'events': list(map(dict, events)), 'drafts': list(map(dict, drafts))}
