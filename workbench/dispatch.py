"""Issue a stable handoff receipt only for an approved current review."""
from . import catalog, evidence, review
from .codec import encode, sha
from .errors import Problem


def _payload(db, case):
    return {'format': 'review-delivery-v1', 'review': case, 'evidence': evidence.export(db, case['run'])}


def issue(db, review_id):
    case = review.get(db, review_id)
    previous = db.execute('SELECT * FROM dispatches WHERE review=?', (review_id,)).fetchone()
    if previous is not None:
        return dict(previous)
    if case['state'] != 'approved':
        raise Problem('dispatch_requires_approval', 409)
    payload = _payload(db, case)
    current = catalog.head(db, case['dataset'])
    if current != {'generation': case['generation'], 'revision': payload['evidence']['result']['revision']}:
        raise Problem('review_activation_changed', 409)
    digest = sha(encode(payload))
    db.execute('INSERT INTO dispatches(review, payload_sha) VALUES (?, ?)', (review_id, digest))
    return dict(db.execute('SELECT * FROM dispatches WHERE review=?', (review_id,)).fetchone())


def download(db, review_id):
    case = review.get(db, review_id)
    receipt = db.execute('SELECT * FROM dispatches WHERE review=?', (review_id,)).fetchone()
    if receipt is None:
        raise Problem('dispatch_not_found', 404)
    payload = _payload(db, case)
    if sha(encode(payload)) != receipt['payload_sha']:
        raise Problem('dispatch_digest_mismatch', 409)
    return {'receipt': dict(receipt), 'payload': payload}
