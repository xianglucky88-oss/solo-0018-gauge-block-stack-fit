"""Fixture-aware recommendations: in-place reconfiguration vs. after-stoppage rebuild.

A workstation keeps part of the gauge stack clamped in the base (locked blocks)
and part removable. Some replacement blocks can only be fetched after the line
is stopped (stoppage-only). This module keeps the two scenarios strictly apart:

* An in-place plan must retain every locked block, may only use blocks already
  mounted or available while the line runs, and must stay within the maximum
  number of remove/add operations.
* A stoppage plan is a free rebuild from the full catalog certified on the
  requested day; it is never presented as an in-place plan.

Every returned block carries the same certificate evidence as the rest of the
service, so both documents can be re-checked against the day's certificates.
"""
from itertools import combinations
from .certificates import number
from .fit import describe, target


def _names(value, label, catalog, allow_empty=False):
    if not isinstance(value, list) or (not allow_empty and not value) or any(
        not isinstance(x, str) for x in value
    ) or len(set(value)) != len(value) or any(x not in catalog for x in value):
        raise ValueError(label)
    return list(value)


def _fixture(doc):
    fixture = doc['fixture']
    catalog = doc['blocks']
    if not isinstance(fixture, dict):
        raise ValueError('fixture')
    if 'max_changes' not in fixture:
        raise ValueError('fixture_max_changes')
    locked_raw = fixture.get('locked', [])
    mounted_raw = fixture.get('mounted')
    stoppage_raw = fixture.get('stoppage_only', [])
    if not isinstance(locked_raw, list) or not isinstance(mounted_raw, list) \
            or not isinstance(stoppage_raw, list):
        raise ValueError('fixture')
    locked = set(_names(locked_raw, 'fixture_locked',
                        catalog, allow_empty=True))
    mounted = set(_names(mounted_raw, 'fixture_mounted', catalog))
    if not locked <= mounted:
        raise ValueError('fixture_locked')
    max_changes = number(fixture['max_changes'], 0, 30, 'fixture_max_changes')
    stoppage_only = set(_names(
        stoppage_raw, 'fixture_stoppage_only', catalog, allow_empty=True,
    ))
    # A stoppage-only block cannot already be sitting in the workstation.
    if stoppage_only & mounted:
        raise ValueError('fixture_stoppage_only')
    return {
        'locked': locked,
        'mounted': mounted,
        'max_changes': max_changes,
        'stoppage_only': stoppage_only,
    }


def _policy_merit(policy, size, margin, changes=None):
    if changes is None:
        return (-size, margin) if policy == 'block_count' else (margin, -size)
    # In-place plans rank by actual remove/add work first (fewer operations is
    # better), then by the original block-count / margin preference. The stable
    # combination enumeration order (sorted block ids) breaks remaining ties.
    if policy == 'block_count':
        return (-changes, -size, margin)
    return (-changes, margin, -size)


def _in_place_row(refs, certified, lower, upper, mounted, locked):
    row = describe(refs, certified, lower, upper)
    removals = sorted(mounted - set(refs))
    additions = sorted(set(refs) - mounted)
    row['in_place'] = {
        'locked_retained': sorted(locked),
        'remove': removals,
        'add': additions,
        'changes': len(removals) + len(additions),
    }
    return row


def _stoppage_plan(good, lower, upper, max_blocks, policy, stoppage_only):
    # A free rebuild over everything certified today. The ranking mirrors the
    # baseline search: block count or margin policy, stable id-order tie breaks;
    # a widest-margin alternative is always reported alongside it.
    plan_view = {
        'feasible_count': 0,
        'recommendation': None,
        'margin_alternative': None,
        'available_blocks': sorted(good),
        'stoppage_only_blocks': sorted(stoppage_only),
    }
    best, widest = None, None
    for size in range(1, max_blocks + 1):
        for refs in combinations(sorted(good), size):
            row = describe(refs, good, lower, upper)
            if row['state'] != 'within':
                continue
            plan_view['feasible_count'] += 1
            merit = _policy_merit(policy, size, row['margin_nm'])
            if best is None or merit > best[0]:
                best = (merit, row)
            wide_merit = (row['margin_nm'], -size)
            if widest is None or wide_merit > widest[0]:
                widest = (wide_merit, row)
    if best is not None:
        plan_view['recommendation'] = best[1]
        plan_view['margin_alternative'] = widest[1]
    return plan_view


def plan(doc, good, bad, max_blocks, policy):
    lower, upper = target(doc)
    fixture = _fixture(doc)
    locked, mounted = fixture['locked'], fixture['mounted']
    max_changes, stoppage_only = fixture['max_changes'], fixture['stoppage_only']

    stoppage = _stoppage_plan(
        good, lower, upper, max_blocks, policy, stoppage_only
    )

    in_place = {
        'blocked_reason': None,
        'blocked_detail': [],
        'feasible_count': 0,
        'recommendation': None,
        'margin_alternative': None,
        'max_changes': max_changes,
        'candidates': [],
    }

    # A locked block whose sole certificate is not usable today can never be
    # part of an in-place plan; name it explicitly instead of silently dropping
    # the clamp and presenting the rebuild as an in-place plan.
    retained_unavailable = sorted(x for x in locked if x not in good)
    if retained_unavailable:
        in_place['blocked_reason'] = 'retained_certificate_unavailable'
        in_place['blocked_detail'] = [
            {'block': x, 'reason': bad.get(x, 'no_valid_certificate')}
            for x in retained_unavailable
        ]
    elif len(locked) > max_blocks:
        in_place['blocked_reason'] = 'fixture_constraint'
        in_place['blocked_detail'] = [
            {'constraint': 'locked_blocks_exceed_max_blocks',
             'locked_count': len(locked), 'max_blocks': max_blocks},
        ]
    else:
        pool = sorted(set(good) - stoppage_only)
        best, widest = None, None
        for size in range(1, max_blocks + 1):
            for refs in combinations(pool, size):
                if not locked <= set(refs):
                    continue
                removals = mounted - set(refs)
                additions = set(refs) - mounted
                changes = len(removals) + len(additions)
                if changes > max_changes:
                    continue
                row = _in_place_row(refs, good, lower, upper, mounted, locked)
                if row['state'] != 'within':
                    continue
                in_place['feasible_count'] += 1
                in_place['candidates'].append(row)
                merit = _policy_merit(policy, size, row['margin_nm'], changes)
                if best is None or merit > best[0]:
                    best = (merit, row)
                # Widest margin within the clamp/change budget; fewer changes and
                # fewer blocks break ties reproducibly.
                wide_merit = (row['margin_nm'], -changes, -size)
                if widest is None or wide_merit > widest[0]:
                    widest = (wide_merit, row)
        if best is not None:
            in_place['recommendation'] = best[1]
            in_place['margin_alternative'] = widest[1]
        else:
            in_place['blocked_reason'] = 'fixture_constraint'
            in_place['blocked_detail'] = [
                {'constraint': 'no_conforming_stack_with_locked_retained',
                 'locked': sorted(locked), 'max_changes': max_changes,
                 'max_blocks': max_blocks},
            ]

    state = (
        'matched_in_place' if in_place['recommendation'] is not None
        else ('stoppage_only' if stoppage['recommendation'] is not None
              else 'no_conforming_stack')
    )
    return {
        'state': state,
        'rank': policy,
        'in_place': in_place,
        'stoppage': stoppage,
        'unusable': bad,
    }
