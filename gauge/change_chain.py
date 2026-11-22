"""Check a same-day change itinerary and evaluate its endpoint delta independently."""
from .stack_delta import compare


def check(doc):
    plan = doc['change_chain']
    steps = plan['steps']
    if not isinstance(steps, list) or not 2 <= len(steps) <= 12:
        raise ValueError('change_chain_length')
    reports, previous = [], doc['stack']
    for step in steps:
        next_stack = step['to']
        comparison = compare({**doc, 'stack': previous, 'comparison_stack': next_stack,
                              'delta_limits_nm': step['limits_nm']})
        reports.append({'from': previous, 'to': next_stack, 'comparison': comparison})
        previous = next_stack
    net = compare({**doc, 'comparison_stack': previous, 'delta_limits_nm': plan['net_limits_nm']})
    all_states = [row['comparison']['state'] for row in reports] + [net['state']]
    state = ('outside' if 'outside' in all_states else 'unresolved' if 'unresolved' in all_states else
             'partial' if 'partial' in all_states else 'within')
    return {'state': state, 'on': doc['on'], 'steps': reports, 'net': net}
