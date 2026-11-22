"""Compare the recommended stack and certificate evidence on requested dates."""
from .certificates import day
from .search import recommend


def days(doc):
    sequence = doc['check_dates']
    if not isinstance(sequence, list) or not 1 <= len(sequence) <= 16:
        raise ValueError('check_dates_count')
    parsed = [day(value) for value in sequence]
    if len(set(parsed)) != len(parsed):
        raise ValueError('check_dates_duplicate')
    return [value.isoformat() for value in sorted(parsed)]


def check(doc):
    rows = [{'on': on, **recommend({**doc, 'on': on})} for on in days(doc)]
    recommendations = [row['recommendation'] for row in rows]
    same = all(p and p['blocks'] == recommendations[0]['blocks'] for p in recommendations) if recommendations[0] else False
    return {'rows': rows, 'all_dates_have_recommendation': all(recommendations), 'same_combination': same}
