from .catalog import version
from .codec import decode, document, sha
from .errors import Problem
from .runs import fetch, result


def export(db, run_id):
    run = fetch(db, run_id)
    revision = version(db, run['revision'])
    intake = db.execute('SELECT source, raw, raw_sha FROM drafts WHERE id=?', (revision['id'],)).fetchone()
    _, canonical, doc_sha, raw_sha = document(intake['raw'])
    if (canonical != revision['document'] or doc_sha != revision['document_sha'] or
            raw_sha != intake['raw_sha'] or sha(run['output']) != run['output_sha']):
        raise Problem('evidence_digest_mismatch', 409)
    event = db.execute("SELECT generation, created FROM publication_events WHERE revision=? AND action='publish'",
                       (revision['id'],)).fetchone()
    return {'format': 'evidence-v1', 'dataset': revision['dataset'], 'source': intake['source'],
            'raw_sha': intake['raw_sha'], 'document_sha': revision['document_sha'],
            'raw': intake['raw'], 'document': decode(revision['document']), 'publication': dict(event),
            'result': result(run)}
