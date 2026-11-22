"""Sweep half-open certificate boundaries and compact adjacent identical states."""
from .certificates import day
from .search import available


def windows(doc):
    available(doc)
    start, end = map(day, doc['availability_window'])
    if start >= end:
        raise ValueError('availability_window')
    edges = {start, end}
    for row in doc['blocks'].values():
        for cert in row['certificates']:
            edges.update(date for date in (day(cert['from']), day(cert['until'])) if start < date < end)
    edges = sorted(edges)
    if len(edges) > 256:
        raise ValueError('availability_boundary_count')
    rows = []
    for a, b in zip(edges, edges[1:]):
        evidence = available({**doc, 'on': a.isoformat()})
        if rows and rows[-1]['status'] == evidence:
            rows[-1]['until'] = b.isoformat()
        else:
            rows.append({'from': a.isoformat(), 'until': b.isoformat(), 'status': evidence})
    return {'segments': rows}
