"""Synthetic scenarios for the reuse-eligibility contract.

Every scenario starts from one fixed previous sheet: the real search
recommendation for ``old_request`` — stack ['B', 'C'] with margin 7 nm
under the margin policy, evidenced by certificates c-b and c-c.  Each
builder returns a fresh new request; nothing mutates shared state, and
each scenario changes exactly one lever (target, ranking policy, one
unselected block's certificate, date, or search scope) unless noted.
"""

BASE_DATE = '2026-11-01'
OLD_STACK = ['B', 'C']
OLD_MARGIN = 7
OLD_EVIDENCE = {'B': 'c-b', 'C': 'c-c'}
OLD_RANK = 'margin'


def cert(cid, frm, until, corr, unc):
    return {'id': cid, 'from': frm, 'until': until,
            'correction_nm': corr, 'uncertainty_nm': unc}


def _block(nominal, *certs):
    return {'nominal_nm': nominal, 'certificates': list(certs)}


def old_request():
    # A:  center 1000003 r5 -> [999998, 1000008], margin 4 under the old target
    # B+C: center 1000001 r4 -> [999997, 1000005], margin 7 (the old winner)
    # D:   center 1000000 r50 -> [999950, 1000050], only partial, never selected
    return {'on': BASE_DATE,
            'blocks': {
                'A': _block(1_000_000, cert('c-a', '2026-01-01', '2027-01-01', 3, 5)),
                'B': _block(400_000, cert('c-b', '2026-01-01', '2027-01-01', 2, 2)),
                'C': _block(600_000, cert('c-c', '2026-01-01', '2027-01-01', -1, 2)),
                'D': _block(1_000_000, cert('c-d', '2026-01-01', '2027-01-01', 0, 50)),
            },
            'target_nm': 1_000_000, 'tolerance_nm': 12,
            'max_blocks': 2, 'rank': OLD_RANK}


# --- target levers -----------------------------------------------------

def target_change_still_winning():
    # New interval [999990, 1000014]: B+C keeps margin 7, A drops to 6.
    req = old_request()
    req['target_nm'] = 1_000_002
    return req


def target_excludes_stack():
    # New interval [1000008, 1000032]: B+C falls completely outside.
    req = old_request()
    req['target_nm'] = 1_000_020
    return req


# --- certificate levers --------------------------------------------------

def challenger_certificate_improves():
    # Only the unselected block D gets a new certificate: center 1000000
    # r4 -> [999996, 1000004], margin 8, outranking the old sheet's 7.
    req = old_request()
    req['blocks']['D'] = _block(1_000_000, cert('c-d2', '2026-01-01', '2027-01-01', 0, 4))
    return req


def unselected_certificate_expires():
    # D has no valid certificate on the date; the old card never used D.
    req = old_request()
    req['blocks']['D'] = _block(1_000_000, cert('c-d', '2026-01-01', '2026-06-01', 0, 50))
    return req


def unselected_certificates_overlap():
    # Two of D's certificates cover the same day; the old card never used D.
    req = old_request()
    req['blocks']['D'] = _block(1_000_000,
                                cert('c-d1', '2026-01-01', '2027-01-01', 0, 50),
                                cert('c-d2', '2026-06-01', '2027-06-01', 0, 40))
    return req


def card_certificate_rolls_over():
    # B's certificate is re-issued the same day: c-b ends at 2026-11-01
    # (exclusive), c-b2 starts at 2026-11-01 (inclusive) with equal values.
    # B stays certified, but the sheet's recorded evidence is stale.
    req = old_request()
    req['blocks']['B'] = _block(400_000,
                                cert('c-b', '2026-01-01', '2026-11-01', 2, 2),
                                cert('c-b2', '2026-11-01', '2027-11-01', 2, 2))
    return req


def card_certificates_overlap_same_day():
    # B (used by the old card) has two certificates covering the date.
    req = old_request()
    req['blocks']['B'] = _block(400_000,
                                cert('c-b', '2026-01-01', '2027-01-01', 2, 2),
                                cert('c-b-dup', '2026-06-01', '2027-06-01', 2, 2))
    return req


# --- date levers (certificate window edges) ------------------------------

def card_certificate_expires_at_edge():
    # c-b/c-c end at 2027-01-01 exclusive: on that day the old card's
    # blocks have no valid certificate.
    req = old_request()
    req['on'] = '2027-01-01'
    return req


def card_certificate_valid_day_before_edge():
    req = old_request()
    req['on'] = '2026-12-31'
    return req


# --- ranking / scope levers ----------------------------------------------

def rank_policy_switches():
    req = old_request()
    req['rank'] = 'block_count'
    return req


def search_scope_shrinks():
    req = old_request()
    req['max_blocks'] = 1
    return req


SCENARIOS = (
    ('target_change_still_winning', target_change_still_winning),
    ('target_excludes_stack', target_excludes_stack),
    ('challenger_certificate_improves', challenger_certificate_improves),
    ('unselected_certificate_expires', unselected_certificate_expires),
    ('unselected_certificates_overlap', unselected_certificates_overlap),
    ('card_certificate_rolls_over', card_certificate_rolls_over),
    ('card_certificates_overlap_same_day', card_certificates_overlap_same_day),
    ('card_certificate_expires_at_edge', card_certificate_expires_at_edge),
    ('card_certificate_valid_day_before_edge', card_certificate_valid_day_before_edge),
    ('rank_policy_switches', rank_policy_switches),
    ('search_scope_shrinks', search_scope_shrinks),
)
