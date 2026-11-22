OPERATION = 'change-chain'
OPTIONAL_FIELD = 'change_chain'


def perturb(doc):
    doc['blocks']['B']['certificates'][0]['uncertainty_nm'] = 3


def verify(before, after):
    assert before['state'] == 'within'
    assert [step['comparison']['difference_nm'] for step in before['steps']] == [
        [400000, 400004], [-400004, -400000]]
    assert before['net']['difference_nm'] == after['net']['difference_nm'] == [0, 0]
    assert [step['comparison']['state'] for step in after['steps']] == ['partial', 'partial']
    assert after['state'] == 'partial'
