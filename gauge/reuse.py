"""Decide whether a previous recommendation sheet still stands.

A virtual workstation operator edits the request — target, ranking
policy, certificates or date — and asks whether the previous
recommendation sheet may be reused as-is.  Three outcomes:

- ``reuse``: the sheet's stack is still fully conforming and is still
  the combination the current certificates and ranking rules would
  recommend; the sheet stands unchanged.
- ``research``: the sheet no longer represents the preferred answer, so
  a new full search is required.
- ``certificate_unavailable``: a block used by the sheet itself has no
  usable certificate on the new date (missing or overlapping), voiding
  the sheet's evidence.  Blocks that were never selected only reshape
  the candidate pool; they never push the decision here.

The decision re-resolves certificates, re-evaluates the sheet's own
stack and checks whether any current challenger would displace it,
exiting at the first one.  It never runs a full search over all
combinations: reuse must mean the sheet still stands, not that a fresh
search was quietly performed and relabelled.
"""
from itertools import combinations
from .certificates import number, resolve
from .fit import describe, target

DECISIONS = ('reuse', 'research', 'certificate_unavailable')
# Causes recorded on every decision: the operator changed the target or
# tolerance, the ranking policy, certificate data (including the date,
# which acts through certificate validity), or the search scope.
CAUSES = ('target', 'rank', 'certificate', 'scope')
_POLICIES = ('block_count', 'margin')


def _policy(doc):
    policy = doc.get('rank', 'block_count')
    if policy not in _POLICIES:
        raise ValueError('rank_policy')
    return policy


def _previous(previous):
    if not isinstance(previous, dict):
        raise ValueError('previous_sheet')
    old_request = previous.get('request')
    sheet = previous.get('sheet')
    if not isinstance(old_request, dict) or not isinstance(sheet, dict):
        raise ValueError('previous_sheet')
    if any(key not in old_request for key in ('on', 'target_nm', 'tolerance_nm', 'blocks')):
        raise ValueError('previous_request')
    old_policy = _policy(old_request)
    if sheet.get('state') != 'matched' or sheet.get('rank', old_policy) != old_policy:
        raise ValueError('previous_sheet')
    rec = sheet.get('recommendation')
    if not isinstance(rec, dict):
        raise ValueError('previous_sheet')
    blocks = rec.get('blocks')
    if (not isinstance(blocks, list) or not 1 <= len(blocks) <= 6
            or any(not isinstance(b, str) or not b.strip() for b in blocks)
            or len(set(blocks)) != len(blocks)):
        raise ValueError('previous_stack')
    evidence = rec.get('evidence')
    if (not isinstance(evidence, dict) or set(evidence) != set(blocks)
            or any(not isinstance(v, str) or not v.strip() for v in evidence.values())):
        raise ValueError('previous_evidence')
    if type(rec.get('margin_nm')) is not int:
        raise ValueError('previous_margin')
    return old_request, {'blocks': blocks, 'evidence': evidence}


def _changes(old, new):
    delta = set()
    if (old['target_nm'], old['tolerance_nm']) != (new['target_nm'], new['tolerance_nm']):
        delta.add('target')
    if _policy(old) != _policy(new):
        delta.add('rank')
    if old['on'] != new['on'] or old['blocks'] != new['blocks']:
        delta.add('certificate')
    if 'max_blocks' in old and old['max_blocks'] != new['max_blocks']:
        delta.add('scope')
    return sorted(delta)


def _displaced(refs, margin, good, lower, upper, max_blocks, policy):
    """True when a currently certified combination would be recommended
    over ``refs``: strictly better merit, or equal merit but earlier in
    the deterministic search order.  Stops at the first challenger."""
    incumbent = tuple(sorted(refs))
    size = len(incumbent)
    for width in range(1, max_blocks + 1):
        if policy == 'block_count' and width > size:
            break  # wider stacks cannot match the incumbent under this policy
        for trial in combinations(sorted(good), width):
            if trial == incumbent:
                continue
            row = describe(trial, good, lower, upper)
            if row['state'] != 'within':
                continue
            edge = row['margin_nm']
            if policy == 'block_count':
                beat = width < size or (width == size and edge > margin)
                tied = width == size and edge == margin and trial < incumbent
            else:
                beat = edge > margin or (edge == margin and width < size)
                tied = edge == margin and width == size and trial < incumbent
            if beat or tied:
                return True
    return False


def decide(doc):
    if not isinstance(doc, dict):
        raise ValueError('expected_object')
    old_request, sheet = _previous(doc.get('previous'))
    request = doc.get('request')
    if not isinstance(request, dict):
        raise ValueError('new_request')
    lower, upper = target(request)
    max_blocks = number(request['max_blocks'], 1, 4, 'max_blocks')
    policy = _policy(request)
    good, bad = resolve(request)
    changes = _changes(old_request, request)
    refs = tuple(sorted(sheet['blocks']))
    card_unusable = {b: bad[b] for b in refs if b in bad}
    card_unusable.update({b: 'no_valid_certificate' for b in refs if b not in good and b not in bad})
    if card_unusable:
        return {'decision': 'certificate_unavailable', 'changes': changes,
                'reasons': ['certificate'], 'stack': list(refs),
                'card_unusable': card_unusable, 'unusable': bad}
    row = describe(refs, good, lower, upper)
    reasons = []
    if len(refs) > max_blocks:
        reasons.append('scope')
    if policy != _policy(old_request):
        reasons.append('rank')
    if any(good[b].certificate != sheet['evidence'][b] for b in refs):
        reasons.append('certificate')
    if row['state'] != 'within':
        reasons.append('target')
    if not reasons and _displaced(refs, row['margin_nm'], good, lower, upper, max_blocks, policy):
        reasons = [cause for cause in ('target', 'certificate', 'scope') if cause in changes] or ['certificate']
    return {'decision': 'reuse' if not reasons else 'research',
            'changes': changes, 'reasons': sorted(reasons), 'stack': list(refs),
            'state': row['state'], 'margin_nm': row['margin_nm'],
            'evidence': {b: good[b].certificate for b in refs}, 'unusable': bad}
