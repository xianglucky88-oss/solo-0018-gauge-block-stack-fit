"""Compare two virtual setups on one date, preserving shared-block identity."""
from .certificates import number, resolve
from .fit import describe, target


def _members(refs, known):
    if (not isinstance(refs, list) or not 1 <= len(refs) <= 6 or any(not isinstance(x, str) for x in refs)
            or len(set(refs)) != len(refs) or set(refs)-known):
        raise ValueError('delta_stack_members')
    return set(refs)


def compare(doc):
    valid, bad = resolve(doc)
    known = valid.keys() | bad.keys()
    before = _members(doc['stack'], known)
    after = _members(doc['comparison_stack'], known)
    lower, upper = (number(value, -10_000_000_000, 10_000_000_000, 'delta_limits') for value in doc['delta_limits_nm'])
    if lower > upper:
        raise ValueError('delta_limit_order')
    unusable = {key: bad[key] for key in sorted(before | after) if key in bad}
    if unusable:
        return {'state': 'unresolved', 'on': doc['on'], 'unusable': unusable}

    shared = sorted(before & after)
    terms, center, radius = [], 0, 0
    for key in sorted(before ^ after):
        cert = valid[key]
        sign = 1 if key in after else -1
        center += sign*cert.center_nm
        radius += cert.uncertainty_nm
        terms.append({'block': key, 'sign': sign, 'certificate': cert.certificate,
                      'center_nm': cert.center_nm, 'uncertainty_nm': cert.uncertainty_nm})
    left, right = center-radius, center+radius
    state = ('within' if lower <= left <= right <= upper else
             'partial' if left <= upper and right >= lower else 'outside')
    target_limits = target(doc)
    evidence = [describe(sorted(refs), valid, *target_limits) for refs in (before, after)]
    absolute = [{'bounds_nm': row['bounds_nm'], 'certificates': row['evidence'], 'state': row['state']}
                for row in evidence]
    return {'state': state, 'on': doc['on'], 'difference_nm': [left, right], 'limits_nm': [lower, upper],
            'before': absolute[0], 'after': absolute[1],
            'common_blocks': shared, 'terms': terms}
