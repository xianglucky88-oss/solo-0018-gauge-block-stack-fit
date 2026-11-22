from copy import deepcopy

from gauge.certificate_drift import reconcile


OPERATION = 'certificate-drift'
OPTIONAL_FIELD = 'certificate_drift'


def perturb(doc):
    certificates = doc['blocks']['A']['certificates']
    fresh = {**certificates[0], 'id': 'c-a-renewed', 'from': '2026-10-31'}
    certificates[0]['until'] = fresh['from']
    certificates.append(fresh)


def verify(before, after):
    assert before['state'] == 'within' and before['measured_change_nm'] == [-1, 3]
    assert before['certificate_change_nm'] == [0, 0] and before['unchanged_blocks'] == ['A']
    assert after['state'] == 'inconclusive' and not after['unchanged_blocks']
    assert after['certificate_change_nm'] == [-14, 14] and after['unexplained_nm'] == [-15, 17]


def edge_cases(doc):
    a = deepcopy(doc)
    a['witness_readings'].pop(0)
    assert reconcile(a)['state'] == 'missing_readings'
    a = deepcopy(doc)
    a['certificate_drift']['dates'][1] = '2026-11-01'
    assert reconcile(a)['state'] == 'witness_conflict'
