from .catalog import head
from .codec import document, encode, sha
from .errors import Problem


def stage(db, ops, name, source, text):
    current = head(db, name)
    if not isinstance(source, str) or not 0 < len(source) <= 120 or not source.isprintable() or '/' in source or '\\' in source:
        raise Problem('source_name')
    _, canonical, doc_sha, raw_sha = document(text)
    token = sha(encode([name, current['generation'], source, raw_sha]))
    existing = db.execute('SELECT state, reason FROM drafts WHERE id=?', (token,)).fetchone()
    if existing:
        state, reason = existing
    else:
        state, reason = 'ready', None
        try:
            ops.validate(canonical)
        except Problem as exc:
            if exc.status != 422:
                raise
            state, reason = 'rejected', exc.body.get('detail', 'domain_input')
        db.execute('''
            INSERT INTO drafts(id, dataset, base, source, raw, raw_sha, document, document_sha, state, reason)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (token, name, current['generation'], source, text, raw_sha, canonical, doc_sha, state, reason))
    return {'id': token, 'dataset': name, 'base': current['generation'], 'state': state, 'reason': reason,
            'document_sha': doc_sha, 'raw_sha': raw_sha}
