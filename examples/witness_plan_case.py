"""Acceptance walk-through for the round-by-round supplementary booking plan.

Canonical commission (all lengths in nm):
* subject delivery deviation window [-4, 4], its selected certificate spans
  [-8, 8] and therefore crosses the delivery tolerance;
* reference certificate spans [-2, 2]; the two combinations use disjoint
  blocks and every device range covers both combinations;
* differential tickets record subject deviation minus reference deviation,
  radius 1, fee 2; absolute tickets cost 8 and have radius 0 here;
* total budget 10, at most two rounds, fees are charged on submission and the
  next round is decided only after the previous reading arrives.

Run:  python3 -B examples/witness_plan_case.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gauge.witness_plan import plan


def commission(received=None):
    return {
        'on': '2026-11-23',
        'blocks': {
            'S': {'nominal_nm': 1_000_000, 'certificates': [
                {'id': 'c-s', 'from': '2026-01-01', 'until': '2027-01-01',
                 'correction_nm': 0, 'uncertainty_nm': 8}]},
            'R': {'nominal_nm': 500_000, 'certificates': [
                {'id': 'c-r', 'from': '2026-01-01', 'until': '2027-01-01',
                 'correction_nm': 0, 'uncertainty_nm': 2}]},
        },
        'target_nm': 1_000_000,
        'tolerance_nm': 4,
        'stack': ['S'],
        'max_blocks': 2,
        'rank': 'margin',
        'witness_plan': {
            'reference_stack': ['R'],
            'budget_fee': 10,
            'max_rounds': 2,
            'devices': [
                {'id': 'abs-1', 'kind': 'absolute', 'target': 'subject',
                 'range_nm': 2_000_000, 'radius_nm': 0, 'fee': 8, 'latest_round': 2},
                {'id': 'diff-1', 'kind': 'differential',
                 'range_nm': 2_000_000, 'radius_nm': 1, 'fee': 2, 'latest_round': 2},
            ],
            'received': received or [],
        },
    }


def by_id(rows, ident):
    key = 'id' if 'id' in rows[0] else 'device'
    return next(row for row in rows if row[key] == ident)


def check_fresh_plan():
    report = plan(commission())
    assert report['state'] == 'undetermined'
    # Certificate intervals are the fixed starting point.
    assert report['subject']['certificate_bounds_nm'] == [-8, 8]
    assert report['subject']['delivery_limits_nm'] == [-4, 4]
    assert report['reference']['certificate_bounds_nm'] == [-2, 2]
    assert report['difference_nm'] == [-10, 10]
    assert report['shared_blocks'] == []
    assert report['rounds'] == {'max': 2, 'last_received': 0, 'next': 1, 'remaining': 2}
    assert report['budget'] == {'limit': 10, 'spent': 0, 'remaining': 10}
    # Both devices are bookable in round one before any order is placed.
    options = report['booking']['options']
    assert {row['device'] for row in options} == {'abs-1', 'diff-1'}
    assert all(row['bookable'] for row in options)
    diff = by_id(options, 'diff-1')
    # A first-round differential cannot guarantee a decision inside two rounds.
    assert diff['conclusive_within_remaining_rounds'] is False
    assert by_id(options, 'abs-1')['conclusive_within_remaining_rounds'] is True
    assert report['booking']['recommended'] == 'diff-1'
    return report


def check_strategy_comparison(fresh):
    strategies = {row['id']: row for row in fresh['strategies']}
    absolute = strategies['absolute_first']
    staged = strategies['differential_then_followup']
    # Direct absolute ticket: fee 8, conclusion always arrives in round one.
    assert absolute['first_round_device'] == 'abs-1'
    assert absolute['first_round_fee'] == 8 and absolute['worst_case_fee'] == 8
    assert absolute['worst_case_round'] == 1 and absolute['guaranteed'] is True
    # Differential first: fee 2, an ambiguous reading needs a round-two absolute.
    assert staged['first_round_device'] == 'diff-1'
    assert staged['first_round_fee'] == 2 and staged['worst_case_fee'] == 10
    assert staged['worst_case_round'] == 2 and staged['guaranteed'] is True
    assert fresh['recommended_strategy'] == 'differential_then_followup'


def check_reading_one():
    # First differential ticket lands at center 1: d in [0, 2].
    report = plan(commission([{'round': 1, 'device': 'diff-1', 'center_nm': 1}]))
    assert report['state'] == 'deliverable'
    assert report['decision']['deliverable'] is True
    # d = x - y, y in [-2, 2] -> x in [d_lo - 2, d_hi + 2] = [-2, 4].
    assert report['subject']['feasible_nm'] == [-2, 4]
    assert report['difference_nm'] == [0, 2]
    assert report['budget']['spent'] == 2 and report['budget']['remaining'] == 8
    # No further booking is needed: the first ticket already settles the stack.
    assert report['booking'] is None and report['stop_reason'] == 'deliverable'
    assert report['decision']['basis_ticket_ids'] == ['r1-diff-1']
    return report


def check_reading_three():
    # First differential ticket lands at center 3: d in [2, 4].
    report = plan(commission([{'round': 1, 'device': 'diff-1', 'center_nm': 3}]))
    # x in [0, 6] crosses the [-4, 4] delivery window: round one must stay open.
    assert report['state'] == 'undetermined'
    assert report['decision']['undetermined'] is True
    assert report['subject']['feasible_nm'] == [0, 6]
    assert report['difference_nm'] == [2, 4]
    assert report['rounds'] == {'max': 2, 'last_received': 1, 'next': 2, 'remaining': 1}
    assert report['budget'] == {'limit': 10, 'spent': 2, 'remaining': 8}
    options = report['booking']['options']
    absolute = by_id(options, 'abs-1')
    differential = by_id(options, 'diff-1')
    # Round two is the final round. An absolute (radius 0) always settles it;
    # another radius-1 differential can still leave an ambiguous reading.
    assert absolute['bookable'] and absolute['conclusive_within_remaining_rounds'] is True
    assert differential['bookable'] and differential['conclusive_within_remaining_rounds'] is False
    # Cheapest booking is still the differential, but only the absolute ticket
    # guarantees an answer in this final round.
    assert report['booking']['recommended'] == 'diff-1'
    assert report['stop_reason'] is None
    # The follow-up total stays inside the remaining budget and round cap.
    assert report['budget']['spent'] + absolute['fee'] == 10
    # Simulate the round-two absolute ticket actually arriving at a good value.
    settled = plan(commission([
        {'round': 1, 'device': 'diff-1', 'center_nm': 3},
        {'round': 2, 'device': 'abs-1', 'center_nm': 2}]))
    assert settled['state'] == 'deliverable'
    assert settled['budget']['spent'] == 10 and settled['booking'] is None
    # The same reading reported as an absolute measured length is equivalent.
    settled_absolute = plan(commission([
        {'round': 1, 'device': 'diff-1', 'center_nm': 3},
        {'round': 2, 'device': 'abs-1', 'center_nm': 1_000_002,
         'scale': 'absolute_length'}]))
    assert settled_absolute['state'] == 'deliverable'
    assert settled_absolute['received'][-1]['interval_nm'] == [2, 2]
    # And a bad absolute value rejects instead of being forced to pass.
    rejected = plan(commission([
        {'round': 1, 'device': 'diff-1', 'center_nm': 3},
        {'round': 2, 'device': 'abs-1', 'center_nm': 6}]))
    assert rejected['state'] == 'rejectable' and rejected['decision']['rejectable'] is True
    return report


def check_conflict_keeps_ticket():
    # A second ticket contradicting the first and the certificates is a conflict:
    # the earlier valid ticket is not dropped and nothing is issued.
    conflict = plan(commission([
        {'round': 1, 'device': 'diff-1', 'center_nm': 1},
        {'round': 2, 'device': 'diff-1', 'center_nm': 12}]))
    assert conflict['state'] == 'witness_conflict'
    assert conflict['conflict'] == {'ticket': 'r2-diff-1',
                                    'reason': 'reading_contradicts_constraints'}
    assert [row['id'] for row in conflict['received']] == ['r1-diff-1']


def check_undetermined_without_capacity():
    # Center 3 then no affordable/legal follow-up: the stack stays undetermined.
    doc = commission([{'round': 1, 'device': 'diff-1', 'center_nm': 3}])
    doc['witness_plan']['devices'][0]['fee'] = 9   # absolute now costs 9 > 8 left
    doc['witness_plan']['devices'][1]['latest_round'] = 1  # differential ends at round one
    report = plan(doc)
    assert report['state'] == 'undetermined'
    absolute = by_id(report['booking']['options'], 'abs-1')
    differential = by_id(report['booking']['options'], 'diff-1')
    assert absolute['bookable'] is False and absolute['blocked_reason'] == ['over_remaining_budget']
    assert differential['bookable'] is False
    assert differential['blocked_reason'] == ['past_latest_round']
    assert report['booking']['recommended'] is None
    assert report['stop_reason'] == 'no_bookable_device'


def check_latest_round_blocks_booking():
    doc = commission()
    doc['witness_plan']['devices'][1]['latest_round'] = 1   # differential only in round one
    first = plan(doc)
    assert first['booking']['round'] == 1
    doc2 = commission([{'round': 1, 'device': 'diff-1', 'center_nm': 3}])
    doc2['witness_plan']['devices'][1]['latest_round'] = 1
    follow = plan(doc2)
    differential = by_id(follow['booking']['options'], 'diff-1')
    assert differential['bookable'] is False
    assert differential['blocked_reason'] == ['past_latest_round']


def check_shared_blocks_share_one_unknown():
    # The same physical block appears in both combinations: it is one unknown,
    # so the differential cancels it instead of treating the two copies as
    # independent extremes.
    doc = {
        'on': '2026-11-23',
        'blocks': {
            'C': {'nominal_nm': 1_000_000, 'certificates': [
                {'id': 'c-c', 'from': '2026-01-01', 'until': '2027-01-01',
                 'correction_nm': 0, 'uncertainty_nm': 4}]},
            'R': {'nominal_nm': 500_000, 'certificates': [
                {'id': 'c-r2', 'from': '2026-01-01', 'until': '2027-01-01',
                 'correction_nm': 0, 'uncertainty_nm': 2}]},
        },
        'target_nm': 1_000_000,
        'tolerance_nm': 4,
        'stack': ['C'],
        'max_blocks': 2,
        'rank': 'margin',
        'witness_plan': {
            'reference_stack': ['C', 'R'],
            'budget_fee': 10,
            'max_rounds': 2,
            'devices': [
                {'id': 'diff-1', 'kind': 'differential', 'range_nm': 2_000_000,
                 'radius_nm': 0, 'fee': 2, 'latest_round': 2},
            ],
            'received': [{'round': 1, 'device': 'diff-1', 'center_nm': 1}],
        },
    }
    report = plan(doc)
    assert report['shared_blocks'] == ['C']
    # d = c - (c + r) = -r, so d = 1 pins the non-shared block r = -1 exactly;
    # the shared block c is one unknown in both stacks and stays free inside
    # its full certificate width [-4, 4].
    assert report['difference_nm'] == [1, 1]
    assert report['block_margins_nm'] == {'C': [-4, 4], 'R': [-1, -1]}
    assert report['subject']['feasible_nm'] == [-4, 4]
    assert report['state'] == 'deliverable'


def check_missing_certificate_unresolved():
    doc = commission()
    doc['blocks']['R']['certificates'][0]['until'] = '2026-11-01'
    report = plan(doc)
    assert report['state'] == 'unresolved_certificate'
    assert report['unusable'] == {'R': 'no_valid_certificate'}


def main():
    fresh = check_fresh_plan()
    check_strategy_comparison(fresh)
    check_reading_one()
    check_reading_three()
    check_conflict_keeps_ticket()
    check_undetermined_without_capacity()
    check_latest_round_blocks_booking()
    check_shared_blocks_share_one_unknown()
    check_missing_certificate_unresolved()
    print('witness-plan: booking schedule and decision checks passed')


if __name__ == '__main__':
    main()
