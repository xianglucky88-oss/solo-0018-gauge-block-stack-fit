"""Retain the certificate used per block for one fixed stack across dates."""
from .fit import check
from .period_check import days
from .search import available


def ledger(doc):
    rows = [{'on': on, **check({**doc, 'on': on})} for on in days(doc)]
    by_block = {block: [] for block in doc['stack']}
    previous = None
    for row in rows:
        availability = available({**doc, 'on': row['on']})
        for block, trail in by_block.items():
            certificate = availability['certified'].get(block, {}).get('certificate')
            reason = availability['unusable'].get(block)
            if previous is None or (trail[-1]['certificate'], trail[-1]['reason']) != (certificate, reason):
                trail.append({'on': row['on'], 'certificate': certificate, 'reason': reason})
        previous = row['on']
    return {'accepted': all(row['state'] == 'within' for row in rows), 'rows': rows, 'changes_by_block': by_block}
