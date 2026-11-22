"""Reconcile synthetic comparator readings with dated stack and target intervals."""
from .certificate_ledger import ledger
from .certificates import day, number
from .fit import target


def inspect(doc):
    readings = doc['witness_readings']
    if not isinstance(readings, list) or not 1 <= len(readings) <= 16:
        raise ValueError('witness_reading_count')
    intervals = {}
    for reading in readings:
        on = day(reading['on']).isoformat()
        center = number(reading['center_nm'], 1, 10_000_000_000, 'witness_center_nm')
        radius = number(reading['uncertainty_nm'], 0, center-1, 'witness_uncertainty_nm')
        if on in intervals:
            raise ValueError('witness_duplicate_date')
        intervals[on] = [center-radius, center+radius]
    lower, upper = target(doc)
    certificate_rows = ledger({**doc, 'check_dates': sorted(intervals)})['rows']
    rows = []
    for row in certificate_rows:
        measured = intervals[row['on']]
        certified = row.get('bounds_nm')
        fits_target = lower <= measured[0] <= measured[1] <= upper
        agreement = max(measured[0], certified[0]) <= min(measured[1], certified[1]) if certified else None
        result = {'on': row['on'], 'measured_nm': measured, 'certified_nm': certified,
                  'measured_in_target': fits_target, 'certificate_state': row['state'], 'agree': agreement}
        if certified is None:
            result.update(state='unresolved_certificate', unusable=row['unusable'])
        else:
            result.update(state='consistent' if agreement else 'disjoint', certificates=row['evidence'])
        rows.append(result)
    return {'target_nm': [lower, upper], 'rows': rows, 'accepted': all(
        row['agree'] and row['measured_in_target'] and row['certificate_state'] == 'within' for row in rows)}
