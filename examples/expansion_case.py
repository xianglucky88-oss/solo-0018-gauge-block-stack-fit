OPERATION = 'stack-delta'
OPTIONAL_FIELD = 'comparison_stack'


def perturb(doc):
    doc['blocks']['B']['certificates'][0]['uncertainty_nm'] = 3


def verify(before, after):
    assert before['state'] == 'within' and before['difference_nm'] == [400000, 400004]
    assert before['common_blocks'] == ['A']
    assert [row['block'] for row in before['terms']] == ['B']
    assert before['before']['bounds_nm'] == [999998, 1000012]
    assert before['after']['bounds_nm'] == [1399998, 1400016]
    assert before['after']['state'] == 'outside'
    assert after['state'] == 'partial' and after['difference_nm'] == [399999, 400005]
    assert after['before'] == before['before']


def edge_cases(doc):
    from gauge.stack_delta import compare

    reverse = compare({**doc, 'stack': doc['comparison_stack'], 'comparison_stack': doc['stack'],
                       'delta_limits_nm': [-400004, -400000]})
    assert reverse['state'] == 'within' and reverse['difference_nm'] == [-400004, -400000]
    unavailable = compare({**doc, 'stack': ['E'], 'comparison_stack': ['E', 'B']})
    assert unavailable['state'] == 'unresolved' and unavailable['unusable'] == {'E': 'overlap'}
    blocks = {**doc['blocks'], 'F': doc['blocks']['A']}
    different = compare({**doc, 'blocks': blocks, 'comparison_stack': ['F'], 'delta_limits_nm': [0, 0]})
    assert different['common_blocks'] == [] and different['difference_nm'] == [-14, 14]
