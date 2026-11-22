"""Plan one shared gauge-block box across two simultaneous workstations.

The first workstation is already committed, so its block order must be issued
before the second workstation's tolerance task is confirmed.  Two candidate
branch tasks are known in advance.  A robust reservation is one *fixed*
first-side stack that leaves a disjoint fully-conforming stack for every
branch.  Branch orders are alternative futures and are never issued together,
so they may name the same block; neither branch order may name a block held by
the first order, which guarantees no block is double-booked at any point.
"""
from itertools import combinations

from .certificates import number, resolve
from .fit import describe, target


def _task(item, default_id):
    if not isinstance(item, dict):
        raise ValueError('task')
    task_id = item.get('id', default_id)
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError('task_id')
    lower, upper = target(item)
    return {
        'id': task_id,
        'target_nm': item['target_nm'],
        'tolerance_nm': item['tolerance_nm'],
        'window_nm': [lower, upper],
    }


def _conforming_stacks(certified, lower, upper, max_blocks):
    rows = []
    for size in range(1, max_blocks + 1):
        for refs in combinations(sorted(certified), size):
            row = describe(refs, certified, lower, upper)
            if row['state'] == 'within':
                rows.append(row)
    # Margin first, then fewer blocks, then stable identifier order.
    rows.sort(key=lambda row: (-row['margin_nm'], len(row['blocks']),
                               tuple(row['blocks'])))
    return rows


def _order_entry(branch_id, first_row, second_row):
    return {
        'branch': branch_id,
        'order': second_row,
        'pair_min_margin_nm': min(first_row['margin_nm'],
                                  second_row['margin_nm']),
        'total_blocks': len(first_row['blocks']) + len(second_row['blocks']),
    }


def plan(doc):
    certified, unusable = resolve(doc)
    max_blocks = number(doc['max_blocks'], 1, 4, 'max_blocks')

    first_task = _task(doc.get('first_task'), 'first')
    raw_branches = doc.get('branches')
    if not isinstance(raw_branches, list) or len(raw_branches) != 2:
        raise ValueError('branches')
    branches = [_task(item, 'branch_%d' % (i + 1))
                for i, item in enumerate(raw_branches)]
    task_ids = [first_task['id']] + [b['id'] for b in branches]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError('task_id')

    first_stacks = _conforming_stacks(certified, *first_task['window_nm'],
                                      max_blocks)
    branch_stacks = {
        branch['id']: _conforming_stacks(
            certified, *branch['window_nm'], max_blocks)
        for branch in branches
    }

    # For every candidate first order, record each branch's best disjoint
    # order (or None when no conforming stack remains on the free blocks).
    options = {}
    feasible_keys = {branch['id']: set() for branch in branches}
    robust_records = []
    for first in first_stacks:
        first_key = tuple(first['blocks'])
        held = set(first['blocks'])
        branch_orders = []
        for branch in branches:
            candidates = [
                row for row in branch_stacks[branch['id']]
                if not held.intersection(row['blocks'])
            ]
            if candidates:
                chosen = candidates[0]
                options[(first_key, branch['id'])] = chosen
                feasible_keys[branch['id']].add(first_key)
                branch_orders.append(
                    _order_entry(branch['id'], first, chosen))
            else:
                options[(first_key, branch['id'])] = None
        if len(branch_orders) == len(branches):
            worst_margin = min(
                [first['margin_nm']]
                + [entry['order']['margin_nm'] for entry in branch_orders])
            worst_total = max(entry['total_blocks']
                              for entry in branch_orders)
            robust_records.append({
                'first_order': first,
                'branch_orders': branch_orders,
                'worst_margin_nm': worst_margin,
                'worst_branch_total_blocks': worst_total,
            })

    robust_records.sort(key=lambda record: (
        -record['worst_margin_nm'],
        record['worst_branch_total_blocks'],
        len(record['first_order']['blocks']),
        tuple(record['first_order']['blocks']),
    ))
    for rank, record in enumerate(robust_records, 1):
        record['rank'] = rank
    robust_keys = {tuple(record['first_order']['blocks'])
                   for record in robust_records}

    # Wait-and-see view: each branch planned as if its task were already
    # confirmed, including first orders that cannot be promised in advance.
    wait_and_see = []
    non_reservable_pairs = []
    for branch in branches:
        branch_id = branch['id']
        joint_plans = []
        for first in first_stacks:
            chosen = options[(tuple(first['blocks']), branch_id)]
            if chosen is not None:
                joint_plans.append((first, chosen))
        entry = {
            'branch': branch_id,
            'jointly_feasible': bool(joint_plans),
            'robust_first_order_blocks': [
                list(key) for key in sorted(robust_keys)],
        }
        if joint_plans:
            first, chosen = sorted(
                joint_plans,
                key=lambda pair: (
                    -min(pair[0]['margin_nm'], pair[1]['margin_nm']),
                    len(pair[0]['blocks']) + len(pair[1]['blocks']),
                    tuple(pair[0]['blocks']),
                    tuple(pair[1]['blocks']),
                ),
            )[0]
            first_key = tuple(first['blocks'])
            entry['best_joint_plan'] = {
                'first_order': first,
                'second_order': chosen,
                'pair_min_margin_nm': min(first['margin_nm'],
                                          chosen['margin_nm']),
                'total_blocks': len(first['blocks']) + len(chosen['blocks']),
                'robust_reservation': first_key in robust_keys,
            }
        blocked_orders = []
        for first in first_stacks:
            first_key = tuple(first['blocks'])
            if (first_key in feasible_keys[branch_id]
                    and first_key not in robust_keys):
                blocked_branches = [
                    other['id'] for other in branches
                    if other['id'] != branch_id
                    and options[(first_key, other['id'])] is None
                ]
                item = {
                    'first_order_blocks': list(first_key),
                    'blocked_branches': blocked_branches,
                }
                blocked_orders.append(item)
                non_reservable_pairs.append({
                    'branch': branch_id,
                    'first_order_blocks': list(first_key),
                    'blocked_branches': blocked_branches,
                })
        entry['non_reservable_first_orders'] = blocked_orders
        wait_and_see.append(entry)

    tasks = [{
        'id': first_task['id'],
        'target_nm': first_task['target_nm'],
        'tolerance_nm': first_task['tolerance_nm'],
        'window_nm': first_task['window_nm'],
        'conforming_count': len(first_stacks),
        'stacks': first_stacks,
    }]
    for branch in branches:
        stacks = branch_stacks[branch['id']]
        tasks.append({
            'id': branch['id'],
            'target_nm': branch['target_nm'],
            'tolerance_nm': branch['tolerance_nm'],
            'window_nm': branch['window_nm'],
            'conforming_count': len(stacks),
            'stacks': stacks,
        })

    return {
        'state': 'reservable' if robust_records
        else 'no_robust_reservation',
        'on': doc['on'],
        'max_blocks': max_blocks,
        'unusable': unusable,
        'tasks': tasks,
        'robust_reservations': robust_records,
        'wait_and_see': wait_and_see,
        'summary': {
            'robust_reservation_count': len(robust_records),
            'non_reservable_simultaneous_pairs': non_reservable_pairs,
        },
    }
