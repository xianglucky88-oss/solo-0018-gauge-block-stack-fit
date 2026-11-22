"""Reconcile measured change with the change explainable by certificate replacement."""
from .certificates import day, number, resolve
from .witness import inspect


def reconcile(doc):
    plan = doc['certificate_drift']
    first, second = plan['dates']
    if day(first) >= day(second):
        raise ValueError('drift_date_order')
    limit = number(plan['max_unexplained_nm'], 0, 10_000_000_000, 'drift_limit')
    records = {row['on']: row for row in inspect(doc)['rows']}
    if first not in records or second not in records:
        return {'state': 'missing_readings', 'dates': [first, second]}
    a, b = records[first], records[second]
    if any(row['state'] == 'unresolved_certificate' for row in (a, b)):
        return {'state': 'unresolved_certificate', 'dates': [first, second], 'witnesses': [a, b]}
    l, r = a['measured_nm']
    x, y = b['measured_nm']
    measured = [x-r, y-l]
    earlier, _ = resolve({**doc, 'on': first})
    later, _ = resolve({**doc, 'on': second})
    changes, unchanged, center, width = [], [], 0, 0
    for key in sorted(doc['stack']):
        old, new = earlier[key], later[key]
        if old == new:
            unchanged.append(key)
            continue
        shift, radius = new.center_nm-old.center_nm, new.uncertainty_nm+old.uncertainty_nm
        center += shift
        width += radius
        changes.append({'block': key, 'before': old.certificate, 'after': new.certificate,
                        'change_nm': [shift-radius, shift+radius]})
    certified = [center-width, center+width]
    residual = [measured[0]-certified[1], measured[1]-certified[0]]
    state = ('witness_conflict' if not (a['agree'] and b['agree']) else
             'within' if -limit <= residual[0] <= residual[1] <= limit else
             'outside' if residual[1] < -limit or residual[0] > limit else 'inconclusive')
    return {'state': state, 'dates': [first, second], 'measured_change_nm': measured,
            'certificate_change_nm': certified, 'unexplained_nm': residual, 'limit_nm': limit,
            'unchanged_blocks': unchanged, 'replaced_certificates': changes}
