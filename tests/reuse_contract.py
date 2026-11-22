"""Executable contract for reuse eligibility, driven through adapters.

The suite is transport-agnostic: concrete test classes bind it to a
Replaceable adapter (see tests/adapters.py).  It drives the three
decision paths — reuse, research, certificate_unavailable — and checks
every decision against the real search and certificate-status workflows
as acceptance controls.  An adapter that always re-searches, always
reuses, or quietly runs a full search on the reuse path cannot pass.
"""
from . import fixtures
from .adapters import AdapterRejected


class ReuseContract:
    """Reuse-eligibility contract.  Subclasses must set adapter_factory."""

    adapter_factory = None

    @classmethod
    def setUpClass(cls):
        cls.adapter = cls.adapter_factory()
        cls.adapter.start()
        cls.old_request = fixtures.old_request()
        # The previous sheet is a real recommendation, not a hand-made one.
        cls.old_sheet = cls.adapter.full_search(cls.old_request)
        cls.previous = {'request': cls.old_request, 'sheet': cls.old_sheet}

    @classmethod
    def tearDownClass(cls):
        cls.adapter.stop()

    def setUp(self):
        self.adapter.reset_counters()

    # -- acceptance oracle -------------------------------------------------

    def assert_matches_real_workflows(self, request, response):
        """The decision must agree with what the real workflows report for
        the same new request, without the reuse path having run them."""
        sheet = self.old_sheet['recommendation']
        stack = sheet['blocks']
        real = self.adapter.full_search(request)
        status = self.adapter.certificate_status(request)
        certified, unusable = status['certified'], status['unusable']
        card_bad = {b for b in stack if b in unusable}
        card_missing = {b for b in stack if b not in certified and b not in unusable}
        if card_bad or card_missing:
            # Only blocks used by the old card may void its certificates.
            self.assertEqual(response['decision'], 'certificate_unavailable')
            self.assertEqual(set(response['card_unusable']), card_bad | card_missing)
            return
        self.assertNotEqual(response['decision'], 'certificate_unavailable',
                            'unselected blocks in trouble must not void the whole card')
        rank_changed = request.get('rank', 'block_count') != fixtures.OLD_RANK
        evidence_stale = any(certified[b]['certificate'] != sheet['evidence'][b] for b in stack)
        scope_shrunk = len(stack) > request['max_blocks']
        winner = real['recommendation']['blocks'] if real['state'] == 'matched' else None
        still_preferred = winner == stack and not rank_changed and not evidence_stale and not scope_shrunk
        expected = 'reuse' if still_preferred else 'research'
        self.assertEqual(response['decision'], expected)
        if expected == 'reuse':
            self.assertEqual(response['margin_nm'], real['recommendation']['margin_nm'])
            self.assertEqual(response['evidence'], sheet['evidence'])

    # -- fixture sanity ------------------------------------------------------

    def test_previous_sheet_is_the_fixed_winner(self):
        sheet = self.old_sheet
        self.assertEqual(sheet['state'], 'matched')
        self.assertEqual(sheet['rank'], fixtures.OLD_RANK)
        self.assertEqual(sheet['recommendation']['blocks'], fixtures.OLD_STACK)
        self.assertEqual(sheet['recommendation']['margin_nm'], fixtures.OLD_MARGIN)
        self.assertEqual(sheet['recommendation']['evidence'], fixtures.OLD_EVIDENCE)

    # -- path 1: reuse --------------------------------------------------------

    def test_reuse_after_target_change(self):
        request = fixtures.target_change_still_winning()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'reuse')
        self.assertEqual(response['changes'], ['target'])
        self.assertEqual(response['reasons'], [])
        self.assertEqual(response['margin_nm'], fixtures.OLD_MARGIN)
        self.assertEqual(response['evidence'], fixtures.OLD_EVIDENCE)
        real = self.adapter.full_search(request)
        self.assertEqual(real['recommendation']['blocks'], fixtures.OLD_STACK)

    def test_reuse_when_unselected_block_loses_certificate(self):
        request = fixtures.unselected_certificate_expires()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'reuse')
        self.assertEqual(response['unusable'], {'D': 'no_valid_certificate'})

    def test_reuse_when_unselected_certificates_overlap(self):
        request = fixtures.unselected_certificates_overlap()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'reuse')
        self.assertEqual(response['unusable'], {'D': 'overlap'})

    def test_reuse_on_the_day_before_the_certificate_edge(self):
        request = fixtures.card_certificate_valid_day_before_edge()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'reuse')

    # -- path 2: research -------------------------------------------------------

    def test_research_when_unselected_certificate_outranks(self):
        # The old winner, its margin and its certificates stay fixed; only
        # one unselected block's certificate changes, so the old sheet is
        # still conforming but loses to another combination.
        request = fixtures.challenger_certificate_improves()
        changed = [name for name in request['blocks']
                   if request['blocks'][name] != self.old_request['blocks'][name]]
        self.assertEqual(changed, ['D'])
        self.assertNotIn('D', fixtures.OLD_STACK)
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'research')
        self.assertEqual(response['changes'], ['certificate'])
        self.assertEqual(response['reasons'], ['certificate'])
        self.assertEqual(response['state'], 'within',
                         'the old recommendation must still be conforming here')
        self.assertEqual(response['margin_nm'], fixtures.OLD_MARGIN)
        real = self.adapter.full_search(request)
        self.assertEqual(real['recommendation']['blocks'], ['D'])
        self.assertNotEqual(real['recommendation']['blocks'], fixtures.OLD_STACK)

    def test_research_when_rank_policy_switches(self):
        request = fixtures.rank_policy_switches()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'research')
        self.assertEqual(response['changes'], ['rank'])
        self.assertEqual(response['reasons'], ['rank'])
        real = self.adapter.full_search(request)
        self.assertEqual(real['recommendation']['blocks'], ['A'])

    def test_research_when_target_excludes_stack(self):
        request = fixtures.target_excludes_stack()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'research')
        self.assertEqual(response['changes'], ['target'])
        self.assertEqual(response['reasons'], ['target'])
        self.assertEqual(response['state'], 'outside')
        real = self.adapter.full_search(request)
        self.assertEqual(real['state'], 'no_conforming_stack')

    def test_research_when_card_certificate_rolls_over(self):
        # B stays certified through a same-day re-issue, but under a new
        # certificate id: the sheet's recorded evidence no longer matches.
        request = fixtures.card_certificate_rolls_over()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'research')
        self.assertEqual(response['changes'], ['certificate'])
        self.assertEqual(response['reasons'], ['certificate'])
        self.assertEqual(response['evidence']['B'], 'c-b2')
        real = self.adapter.full_search(request)
        self.assertEqual(real['recommendation']['blocks'], fixtures.OLD_STACK)

    def test_research_when_search_scope_shrinks(self):
        request = fixtures.search_scope_shrinks()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'research')
        self.assertEqual(response['changes'], ['scope'])
        self.assertEqual(response['reasons'], ['scope'])

    # -- path 3: certificate_unavailable ---------------------------------------

    def test_card_unavailable_at_certificate_window_edge(self):
        # c-b/c-c end at 2027-01-01 exclusive: exactly on that day the old
        # card's blocks have no valid certificate.
        request = fixtures.card_certificate_expires_at_edge()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'certificate_unavailable')
        self.assertEqual(response['reasons'], ['certificate'])
        self.assertEqual(response['card_unusable'],
                         {'B': 'no_valid_certificate', 'C': 'no_valid_certificate'})
        status = self.adapter.certificate_status(request)
        self.assertEqual(status['unusable']['B'], 'no_valid_certificate')
        self.assertEqual(status['unusable']['C'], 'no_valid_certificate')

    def test_card_unavailable_on_same_day_overlap(self):
        request = fixtures.card_certificates_overlap_same_day()
        response = self.adapter.decide(self.previous, request)
        self.assertEqual(response['decision'], 'certificate_unavailable')
        self.assertEqual(response['card_unusable'], {'B': 'overlap'})
        status = self.adapter.certificate_status(request)
        self.assertEqual(status['unusable']['B'], 'overlap')

    def test_only_card_blocks_trigger_unavailability(self):
        # The same certificate trouble (missing or overlapping) must void the
        # card when it hits a used block, and must not when it does not.
        for build in (fixtures.unselected_certificate_expires,
                      fixtures.unselected_certificates_overlap):
            response = self.adapter.decide(self.previous, build())
            self.assertNotEqual(response['decision'], 'certificate_unavailable')
        for build in (fixtures.card_certificate_expires_at_edge,
                      fixtures.card_certificates_overlap_same_day):
            response = self.adapter.decide(self.previous, build())
            self.assertEqual(response['decision'], 'certificate_unavailable')

    # -- independent checks ------------------------------------------------------

    def test_certificate_window_edges(self):
        # Left-closed, right-open windows, checked independently of any sheet.
        block = {'X': {'nominal_nm': 1000,
                       'certificates': [fixtures.cert('c-x', '2026-11-01', '2026-11-22', 0, 1)]}}
        for on, usable in (('2026-10-31', False), ('2026-11-01', True),
                           ('2026-11-21', True), ('2026-11-22', False)):
            with self.subTest(on=on):
                status = self.adapter.certificate_status({'on': on, 'blocks': block})
                if usable:
                    self.assertIn('X', status['certified'])
                else:
                    self.assertEqual(status['unusable'], {'X': 'no_valid_certificate'})

    def test_same_day_overlap_marks_the_block_unusable(self):
        block = {'X': {'nominal_nm': 1000,
                       'certificates': [fixtures.cert('c-x1', '2026-11-01', '2026-11-22', 0, 1),
                                        fixtures.cert('c-x2', '2026-11-22', '2026-12-01', 0, 1)]}}
        # The two windows only touch: 2026-11-22 belongs to c-x2 alone.
        status = self.adapter.certificate_status({'on': '2026-11-22', 'blocks': block})
        self.assertEqual(status['certified']['X']['certificate'], 'c-x2')
        block['X']['certificates'][0]['until'] = '2026-11-23'  # now both cover the day
        status = self.adapter.certificate_status({'on': '2026-11-22', 'blocks': block})
        self.assertEqual(status['unusable'], {'X': 'overlap'})

    def test_causes_are_recorded_separately(self):
        cases = {'target': fixtures.target_excludes_stack,
                 'rank': fixtures.rank_policy_switches,
                 'certificate': fixtures.challenger_certificate_improves}
        for cause, build in cases.items():
            with self.subTest(cause=cause):
                response = self.adapter.decide(self.previous, build())
                self.assertEqual(response['decision'], 'research')
                self.assertEqual(response['reasons'], [cause])
                self.assertEqual(response['changes'], [cause])

    # -- acceptance controls ------------------------------------------------------

    def test_decision_agrees_with_real_new_request(self):
        for name, build in fixtures.SCENARIOS:
            with self.subTest(scenario=name):
                self.assert_matches_real_workflows(build(), self.adapter.decide(self.previous, build()))

    def test_reuse_path_performs_no_full_search(self):
        for name, build in fixtures.SCENARIOS:
            with self.subTest(scenario=name):
                request = build()
                before = self.adapter.full_search_calls()
                self.adapter.decide(self.previous, request)
                self.assertEqual(self.adapter.full_search_calls(), before,
                                 'the reuse path must not run a full search')
                self.adapter.full_search(request)  # liveness: the counter works
                self.assertEqual(self.adapter.full_search_calls(), before + 1)

    # -- input validation ----------------------------------------------------------

    def test_invalid_previous_sheet_is_rejected(self):
        bad = {'request': self.old_request,
               'sheet': {'state': 'no_conforming_stack', 'recommendation': None, 'rank': fixtures.OLD_RANK}}
        with self.assertRaises(AdapterRejected):
            self.adapter.decide(bad, fixtures.old_request())

    def test_unknown_rank_policy_is_rejected(self):
        request = fixtures.old_request()
        request['rank'] = 'cheapest'
        with self.assertRaises(AdapterRejected):
            self.adapter.decide(self.previous, request)
