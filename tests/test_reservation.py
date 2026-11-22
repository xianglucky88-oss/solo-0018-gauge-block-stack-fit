"""Behavioral checks for the shared-box reservation planner."""
import copy
import json
import unittest
from pathlib import Path

from gauge import reservation
from gauge.http_api import ROUTES, server

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'shared_reservation.json'


def load():
    return json.loads(EXAMPLE.read_text(encoding='utf-8'))


def block_keys(records):
    return [record['first_order']['blocks'] for record in records]


class SharedReservationExampleTests(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.out = reservation.plan(self.doc)

    def test_certificate_status_rejects_overlap_and_gaps(self):
        self.assertEqual(self.out['unusable'], {
            'H': 'no_valid_certificate',
            'I': 'overlap',
            'J': 'no_valid_certificate',
        })
        used = set()
        for task in self.out['tasks']:
            for stack in task['stacks']:
                used.update(stack['blocks'])
        self.assertFalse(used & {'H', 'I', 'J'})

    def test_state_is_reservable_with_two_robust_orders(self):
        self.assertEqual(self.out['state'], 'reservable')
        self.assertEqual(self.out['summary']['robust_reservation_count'], 2)
        self.assertEqual(block_keys(self.out['robust_reservations']),
                         [['A'], ['G']])

    def test_ranking_uses_worst_margin_then_block_count_then_identifier(self):
        ranks = self.out['robust_reservations']
        self.assertEqual(ranks[0]['worst_margin_nm'], 2)
        self.assertEqual(ranks[0]['worst_branch_total_blocks'], 3)
        self.assertTrue(
            ranks[0]['worst_margin_nm'] >= ranks[1]['worst_margin_nm'])
        # Tied worst margin and block count: stable identifier A before G.
        self.assertEqual(ranks[0]['first_order']['blocks'], ['A'])
        self.assertEqual(ranks[1]['first_order']['blocks'], ['G'])

    def test_every_branch_order_is_disjoint_from_the_first_order(self):
        for record in self.out['robust_reservations']:
            held = set(record['first_order']['blocks'])
            for entry in record['branch_orders']:
                self.assertFalse(held & set(entry['order']['blocks']))
                self.assertEqual(entry['order']['state'], 'within')

    def test_branch_orders_are_per_branch_and_evidence_is_complete(self):
        top = self.out['robust_reservations'][0]
        by_branch = {entry['branch']: entry for entry in top['branch_orders']}
        self.assertEqual(sorted(by_branch), ['T1', 'T2'])
        self.assertEqual(by_branch['T1']['order']['blocks'], ['B', 'C'])
        self.assertEqual(by_branch['T2']['order']['blocks'], ['C'])
        # Alternative futures may reuse a block; the shared first order may not.
        self.assertIn('C', by_branch['T1']['order']['blocks'])
        self.assertIn('C', by_branch['T2']['order']['blocks'])
        for entry in top['branch_orders']:
            self.assertEqual(
                set(entry['order']['evidence']),
                set(entry['order']['blocks']))

    def test_wait_and_see_lists_pairs_that_cannot_be_promised_early(self):
        by_branch = {w['branch']: w for w in self.out['wait_and_see']}
        self.assertTrue(by_branch['T1']['jointly_feasible'])
        self.assertEqual(by_branch['T1']['non_reservable_first_orders'], [])
        t2 = by_branch['T2']
        blocked = [item['first_order_blocks']
                   for item in t2['non_reservable_first_orders']]
        self.assertEqual(blocked, [
            ['B', 'C', 'K'],
            ['B', 'C', 'E'],
            ['B', 'D', 'E', 'K'],
            ['B', 'E', 'F', 'K'],
        ])
        for item in t2['non_reservable_first_orders']:
            self.assertEqual(item['blocked_branches'], ['T1'])
        self.assertEqual(
            [pair['first_order_blocks']
             for pair in self.out['summary']
             ['non_reservable_simultaneous_pairs']],
            blocked)
        self.assertTrue(
            all(pair['branch'] == 'T2'
                for pair in self.out['summary']
                ['non_reservable_simultaneous_pairs']))

    def test_partial_intersections_are_excluded_from_conforming_sets(self):
        for task in self.out['tasks']:
            self.assertTrue(all(s['margin_nm'] >= 0 for s in task['stacks']))
            self.assertEqual(task['conforming_count'], len(task['stacks']))


class NoRobustReservationTests(unittest.TestCase):
    def test_first_order_holding_every_branch_block_is_not_reservable(self):
        # T0's only conforming first order is [X]; both branch tasks each
        # have one conforming order ([Y], [Z]) disjoint from X, so waiting
        # for confirmation always allows simultaneous work, but no single
        # first order can be reserved against both unknown branches.
        # Corrections break the symmetry between the two 10-blocks: W has
        # center 11, X has center 9.  T1's conforming orders all need X,
        # T2's all need W, so no first order can be promised against both
        # unknown branches; after confirmation each branch still pairs with
        # a disjoint alternative first order.
        doc = {
            'on': '2026-11-22',
            'max_blocks': 2,
            'first_task': {'id': 'T0', 'target_nm': 10, 'tolerance_nm': 1},
            'branches': [
                {'id': 'T1', 'target_nm': 14, 'tolerance_nm': 0},
                {'id': 'T2', 'target_nm': 16, 'tolerance_nm': 0},
            ],
            'blocks': {
                'X': {'nominal_nm': 10, 'certificates': [
                    {'id': 'cx', 'from': '2026-01-01', 'until': '2027-01-01',
                     'correction_nm': -1, 'uncertainty_nm': 0}]},
                'W': {'nominal_nm': 10, 'certificates': [
                    {'id': 'cw', 'from': '2026-01-01', 'until': '2027-01-01',
                     'correction_nm': 1, 'uncertainty_nm': 0}]},
                'Y': {'nominal_nm': 5, 'certificates': [
                    {'id': 'cy', 'from': '2026-01-01', 'until': '2027-01-01',
                     'correction_nm': 0, 'uncertainty_nm': 0}]},
                'Z': {'nominal_nm': 5, 'certificates': [
                    {'id': 'cz', 'from': '2026-01-01', 'until': '2027-01-01',
                     'correction_nm': 0, 'uncertainty_nm': 0}]},
            },
        }
        out = reservation.plan(doc)
        self.assertEqual(
            [s['blocks'] for s in out['tasks'][0]['stacks']],
            [['Y', 'Z'], ['W'], ['X']])
        self.assertEqual(
            [s['blocks'] for s in out['tasks'][1]['stacks']],
            [['X', 'Y'], ['X', 'Z']])
        self.assertEqual(
            [s['blocks'] for s in out['tasks'][2]['stacks']],
            [['W', 'Y'], ['W', 'Z']])
        self.assertEqual(out['state'], 'no_robust_reservation')
        self.assertEqual(out['robust_reservations'], [])
        # Wait-and-see still allows simultaneous work per branch, but the
        # only viable first orders cannot be promised in advance.
        by_branch = {w['branch']: w for w in out['wait_and_see']}
        self.assertTrue(by_branch['T1']['jointly_feasible'])
        self.assertTrue(by_branch['T2']['jointly_feasible'])
        for view in by_branch.values():
            self.assertEqual(view['robust_first_order_blocks'], [])
        self.assertEqual(
            [item['first_order_blocks']
             for item in by_branch['T1']['non_reservable_first_orders']],
            [['W']])
        self.assertEqual(
            [item['first_order_blocks']
             for item in by_branch['T2']['non_reservable_first_orders']],
            [['X']])
        self.assertEqual(
            [(p['branch'], p['first_order_blocks'])
             for p in out['summary']['non_reservable_simultaneous_pairs']],
            [('T1', ['W']), ('T2', ['X'])])
        # Best wait-and-see joint plans are genuinely disjoint.
        self.assertEqual(
            by_branch['T1']['best_joint_plan']['first_order']['blocks'],
            ['W'])
        self.assertEqual(
            by_branch['T1']['best_joint_plan']['second_order']['blocks'],
            ['X', 'Y'])
        self.assertEqual(
            by_branch['T2']['best_joint_plan']['first_order']['blocks'],
            ['X'])
        self.assertEqual(
            by_branch['T2']['best_joint_plan']['second_order']['blocks'],
            ['W', 'Y'])


class InputValidationTests(unittest.TestCase):
    def test_requires_exactly_two_branches(self):
        doc = load()
        doc['branches'] = doc['branches'][:1]
        with self.assertRaises(ValueError):
            reservation.plan(doc)

    def test_rejects_duplicate_task_ids(self):
        doc = load()
        doc['branches'][0]['id'] = 'T0'
        with self.assertRaises(ValueError):
            reservation.plan(doc)

    def test_rejects_max_blocks_above_four(self):
        doc = load()
        doc['max_blocks'] = 5
        with self.assertRaises(ValueError):
            reservation.plan(doc)

    def test_deep_copy_does_not_mutate_input(self):
        doc = load()
        before = copy.deepcopy(doc)
        reservation.plan(doc)
        self.assertEqual(doc, before)


class HttpRouteTests(unittest.TestCase):
    def test_route_registered_and_served(self):
        self.assertIn('/stackfit/shared-reservation', ROUTES)
        payload = EXAMPLE.read_bytes()
        with server(0) as listener:
            import threading
            import urllib.request
            handler = threading.Thread(
                target=listener.handle_request, daemon=True)
            handler.start()
            req = urllib.request.Request(
                f'http://127.0.0.1:{listener.server_port}'
                '/stackfit/shared-reservation',
                data=payload, headers={'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=5) as response:
                body = json.loads(response.read().decode('utf-8'))
            handler.join(timeout=4)
        self.assertEqual(body['state'], 'reservable')
        self.assertEqual(
            body['robust_reservations'][0]['first_order']['blocks'], ['A'])


if __name__ == '__main__':
    unittest.main()
