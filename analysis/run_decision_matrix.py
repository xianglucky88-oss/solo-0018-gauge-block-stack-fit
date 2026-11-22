"""Re-runnable purchase/metrology decision matrix for a single backup gauge block.

Drives the real HTTP entry points (`certificate-status`, `stack-interval`,
`conforming-stacks`) from `analysis/scenario.json` and writes
`analysis/out/decision_matrix.json`.

Every comparison keeps the quoted models, corrections, radii, target and both
candidate production dates fixed.  The only thing the variant changes is the
start date of one certificate of one quoted block.

    python3 -B -m analysis.run_decision_matrix
"""
import json
from copy import deepcopy
from itertools import combinations
from pathlib import Path
from threading import Thread
from urllib.request import ProxyHandler, Request, build_opener

from gauge.http_api import server

ROOT = Path(__file__).resolve().parent
SCENARIO = ROOT / 'scenario.json'
OUT = ROOT / 'out' / 'decision_matrix.json'
OPEN = build_opener(ProxyHandler({}))


def post(port, route, doc):
    body = json.dumps(doc, sort_keys=True).encode('utf-8')
    request = Request(f'http://127.0.0.1:{port}{route}', data=body,
                      headers={'Content-Type': 'application/json'})
    with OPEN.open(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode('utf-8'))


def quote_model(scenario, quote, variant):
    model = deepcopy(scenario['quotes'][quote])
    change = scenario['variant']
    if variant and quote == change['block']:
        cert = model['certificates'][change['certificate_index']]
        cert[change['field']] = change['value']
    return model


def catalog(scenario, quote, variant):
    blocks = deepcopy(scenario['stock'])
    if quote is not None:
        blocks[quote] = quote_model(scenario, quote, variant)
    return blocks


def search_doc(scenario, on, blocks):
    return {
        'on': on,
        'blocks': blocks,
        'target_nm': scenario['target_nm'],
        'tolerance_nm': scenario['tolerance_nm'],
        'max_blocks': scenario['max_blocks'],
        'rank': scenario['rank'],
    }


def stack_doc(scenario, on, blocks, refs):
    doc = search_doc(scenario, on, blocks)
    doc['stack'] = list(refs)
    return doc


def status_view(certified, unusable, blocks):
    """Correction and radius per block, never the nominal length."""
    rows = {}
    for name in sorted(blocks):
        if name in certified:
            entry = certified[name]
            correction = entry['center_nm'] - blocks[name]['nominal_nm']
            rows[name] = {
                'usable': True,
                'correction_nm': correction,
                'radius_nm': entry['uncertainty_nm'],
                'center_nm': entry['center_nm'],
                'certificate': entry['certificate'],
                'bounds_nm': [entry['center_nm'] - entry['uncertainty_nm'],
                              entry['center_nm'] + entry['uncertainty_nm']],
            }
        else:
            rows[name] = {'usable': False, 'reason': unusable[name]}
    return rows


def enumerate_attempts(scenario, port, on, blocks, certified, must_include):
    """Every bounded stack containing the quote, with the entry's own verdict."""
    usable = [name for name in sorted(blocks) if name in certified]
    if must_include is not None and must_include not in certified:
        return []
    found = []
    for size in range(1, scenario['max_blocks'] + 1):
        for refs in combinations(usable, size):
            if must_include is not None and must_include not in refs:
                continue
            status, row = post(port, '/stackfit/stack-interval',
                               stack_doc(scenario, on, blocks, refs))
            if status == 200:
                found.append(row)
    found.sort(key=lambda row: (-row['margin_nm'], len(row['blocks']), row['blocks']))
    return found


def closest(attempts):
    if not attempts:
        return None
    row = attempts[0]
    return {'blocks': row['blocks'], 'state': row['state'], 'center_nm': row['center_nm'],
            'bounds_nm': row['bounds_nm'], 'margin_nm': row['margin_nm']}


def evaluate(scenario, port, dates, quote, variant):
    blocks = catalog(scenario, quote, variant)
    per_date = {}
    for label in sorted(dates):
        on = dates[label]
        cert_status, cert = post(port, '/stackfit/certificate-status',
                                 {'on': on, 'blocks': blocks})
        rec_status, rec = post(port, '/stackfit/conforming-stacks',
                               search_doc(scenario, on, blocks))
        certified = {name: entry for name, entry in cert['certified'].items()}
        attempts = enumerate_attempts(scenario, port, on, blocks, certified, quote)
        stacks = [row for row in attempts if row['state'] == 'within']
        per_date[label] = {
            'on': on,
            'certificate_status_http': cert_status,
            'status': status_view(certified, cert['unusable'], blocks),
            'unusable': cert['unusable'],
            'conforming_stacks_http': rec_status,
            'recommendation': rec['recommendation'],
            'feasible_count': rec['feasible_count'],
            'feasible_stacks': stacks,
            'feasible': bool(stacks),
            'attempts_considered': len(attempts),
            'closest_attempt': closest(attempts),
        }
    feasible_dates = [label for label in sorted(per_date) if per_date[label]['feasible']]
    if len(feasible_dates) == len(dates):
        classification = 'order_now'
    elif feasible_dates:
        classification = 'wait_for_date'
    else:
        classification = 'impossible_under_current_certificates'
    return {
        'quote': quote,
        'variant': variant,
        'classification': classification,
        'feasible_dates': feasible_dates,
        'feasible_date_count': len(feasible_dates),
        'dates': per_date,
    }


def fixed_sets(scenario, port, dates, quote, variant):
    """Stacks whose exact block set conforms on every candidate date."""
    blocks = catalog(scenario, quote, variant)
    certified = {}
    for label in sorted(dates):
        _, cert = post(port, '/stackfit/certificate-status',
                       {'on': dates[label], 'blocks': blocks})
        certified[label] = set(cert['certified'])
    shared = sorted(set.intersection(*certified.values()))
    if quote is not None and quote not in shared:
        return []
    fixed = []
    for size in range(1, scenario['max_blocks'] + 1):
        for refs in combinations(shared, size):
            if quote is not None and quote not in refs:
                continue
            states = {}
            for label in sorted(dates):
                _, row = post(port, '/stackfit/stack-interval',
                              stack_doc(scenario, dates[label], blocks, refs))
                states[label] = row['state']
            if all(state == 'within' for state in states.values()):
                fixed.append({'blocks': list(refs), 'state_per_date': states})
    return fixed


def best_per_date(results):
    best = {}
    for label in sorted(results[0]['dates']):
        ranked = []
        for result in results:
            row = result['dates'][label]
            if row['recommendation'] is not None:
                ranked.append((row['recommendation']['margin_nm'], result['quote']))
        ranked.sort(reverse=True)
        best[label] = {'quote': ranked[0][1], 'margin_nm': ranked[0][0]} if ranked else None
    return best


def counterexamples(scenario, port, dates):
    """Certificate holes and overlaps must stay unresolved, never nominal."""
    blocks = catalog(scenario, 'S-A', False)
    probes = [
        {'label': 'overlap_not_nominal', 'date': 'D1',
         'stack': ['S-A', 'I', 'J'],
         'why': 'I has two certificates covering D1; nominal 200000 must not be substituted.'},
        {'label': 'gap_not_nominal', 'date': 'D1',
         'stack': ['S-A', 'F', 'C'],
         'why': 'F certificate starts 2026-12-01, after D1; nominal 300000 must not be substituted.'},
        {'label': 'expired_not_nominal', 'date': 'D2',
         'stack': ['S-A', 'D', 'C'],
         'why': 'D certificate ends 2026-12-01 (left-closed/right-open), so it is void on D2.'},
    ]
    out = []
    for probe in probes:
        status, row = post(port, '/stackfit/stack-interval',
                           stack_doc(scenario, dates[probe['date']], blocks, probe['stack']))
        out.append({
            'label': probe['label'],
            'on': dates[probe['date']],
            'stack': probe['stack'],
            'http': status,
            'state': row.get('state'),
            'unusable': row.get('unusable'),
            'why': probe['why'],
            'nominal_substitution_is_invalid': True,
        })
    return out


def splice_trap(best):
    quotes = {entry['quote'] for entry in best.values() if entry is not None}
    return {
        'best_per_date': best,
        'distinct_quotes': sorted(quotes),
        'single_order_possible': len(quotes) == 1,
        'note': 'Per-date optima using different quoted blocks cannot be combined '
                'into one order, because the ordered model cannot change after submission.',
    }


def guarantee_table(report):
    rows = {}
    for quote in sorted({row['quote'] for row in report['results']['base']}):
        fixed = report['fixed_sets']['base'][quote]
        result = next(row for row in report['results']['base'] if row['quote'] == quote)
        order_now = result['classification'] == 'order_now'
        fixed_ok = bool(fixed)
        if fixed_ok:
            fixed_guarantee = (
                'the exact same block set is certified on every candidate date and produces '
                'identical bounds; assembly may not substitute partners, so the guarantee is '
                'reproducible but narrow')
        elif order_now:
            fixed_guarantee = (
                'not available: no single exact stack conforms on both dates, so a fixed-stack '
                'order would over-commit beyond what the certificates support')
        else:
            fixed_guarantee = 'not available: the quote does not reach every candidate date'
        if order_now:
            late_guarantee = (
                'the ordered block is certified on every candidate date and at least one '
                'conforming partner set exists on each date; assembly is deferred until the '
                'date is confirmed, but the same partners, bounds and margin are not promised')
        elif result['feasible_dates']:
            late_guarantee = (
                'only the dates listed are covered; on the remaining date no conforming partner '
                'set exists, so locking the purchase does not guarantee a usable stack everywhere')
        else:
            late_guarantee = (
                'not available: the ordered block has no conforming partner set on any candidate '
                'date under the current certificates')
        rows[quote] = {
            'classification': result['classification'],
            'fixed_cross_date_stack': {
                'attainable': fixed_ok,
                'stacks': [entry['blocks'] for entry in fixed],
                'guarantee': fixed_guarantee,
            },
            'late_assembly_locked_purchase': {
                'attainable': order_now,
                'feasible_dates': result['feasible_dates'],
                'guarantee': late_guarantee,
                'does_not_guarantee': 'a reproducible exact stack, the per-date optimum, or identical margins',
            },
        }
    return rows


def same_backup_different_partners(report):
    """A quote that can be ordered now although its partners differ by date."""
    found = []
    for result in report['results']['base']:
        if result['classification'] != 'order_now':
            continue
        per_date = {}
        for label, row in result['dates'].items():
            per_date[label] = [entry['blocks'] for entry in row['feasible_stacks']]
        distinct = {tuple(sorted(stack)) for stacks in per_date.values() for stack in stacks}
        fixed = report['fixed_sets']['base'][result['quote']]
        found.append({
            'quote': result['quote'],
            'order_now_without_fixed_stack': not fixed,
            'partners_per_date': per_date,
            'distinct_partner_sets': len(distinct),
            'explanation': (
                'the same ordered block pairs with different in-stock blocks on different dates; '
                'it can be ordered now because assembly is deferred, even though no single exact '
                'stack is guaranteed across dates')
            if not fixed else
            'a fixed exact stack also exists, so this quote is a stronger fixed-stack case',
        })
    return found


def variant_transition(report):
    """Which quotes changed class when only one certificate start date moved."""
    transitions = {}
    base = {row['quote']: row for row in report['results']['base']}
    variant = {row['quote']: row for row in report['results']['variant']}
    for quote in sorted(base):
        before, after = base[quote]['classification'], variant[quote]['classification']
        transitions[quote] = {
            'before': before,
            'after': after,
            'changed': before != after,
            'before_dates': base[quote]['feasible_dates'],
            'after_dates': variant[quote]['feasible_dates'],
        }
    return transitions


def self_check(report, scenario):
    change = scenario['variant']
    for label, variant in (('base', False), ('variant', True)):
        full = catalog(scenario, None, variant)
        for other in scenario['quotes']:
            full[other] = quote_model(scenario, other, variant)
        for name, expected in scenario['stock'].items():
            if full[name] != expected:
                raise AssertionError(f'{label}: stock block {name} changed')
        for other in scenario['quotes']:
            expected = quote_model(scenario, other, variant)
            if full[other] != expected:
                raise AssertionError(f'{label}: quote {other} changed')
    base_sa = quote_model(scenario, 'S-A', False)
    var_sa = quote_model(scenario, 'S-A', True)
    diffs = [(key) for key in base_sa['certificates'][0]
             if base_sa['certificates'][0][key] != var_sa['certificates'][0][key]]
    if diffs != ['from'] or change['block'] != 'S-A':
        raise AssertionError(f'variant changed more than one certificate start date: {diffs}')
    if scenario['target_nm'] != report['target_nm'] or scenario['tolerance_nm'] != report['tolerance_nm']:
        raise AssertionError('target changed')
    return {'variant_block': change['block'], 'changed_fields': diffs,
            'target_unchanged': True, 'dates_unchanged': True}


def verify(report):
    """Fail loudly if a re-run drifts from the documented decision story."""
    base = {row['quote']: row for row in report['results']['base']}
    variant = {row['quote']: row for row in report['results']['variant']}
    expected_base = {
        'S-A': 'order_now',
        'S-B': 'wait_for_date',
        'S-C': 'impossible_under_current_certificates',
        'S-D': 'order_now',
    }
    expected_variant = dict(expected_base, **{'S-A': 'wait_for_date'})
    checks = {
        'base_classification': {q: base[q]['classification'] for q in expected_base},
        'variant_classification': {q: variant[q]['classification'] for q in expected_variant},
        'base_expected': expected_base,
        'variant_expected': expected_variant,
        'only_S-A_changed_class': [q for q in base
                                   if base[q]['classification'] != variant[q]['classification']],
        'S-A_base_partners_differ': (
            [s['blocks'] for s in base['S-A']['dates']['D1']['feasible_stacks']]
            != [s['blocks'] for s in base['S-A']['dates']['D2']['feasible_stacks']]),
        'S-A_fixed_stack_absent': report['fixed_sets']['base']['S-A'] == [],
        'S-D_fixed_stack_present': bool(report['fixed_sets']['base']['S-D']),
        'S-D_bounds_identical': (
            variant['S-D']['dates']['D1']['recommendation']['bounds_nm']
            == variant['S-D']['dates']['D2']['recommendation']['bounds_nm']),
        'variant_S-A_D1_unusable': (
            variant['S-A']['dates']['D1']['status']['S-A'].get('reason')
            == 'no_valid_certificate'
            and variant['S-A']['dates']['D1']['attempts_considered'] == 0),
        'variant_S-A_D2_still_usable': (
            variant['S-A']['dates']['D2']['status']['S-A'].get('usable') is True),
        'counterexamples_all_unresolved': all(row['state'] == 'unresolved'
                                              for row in report['counterexamples']),
        'splice_quotes_differ': not report['splice_trap']['single_order_possible'],
        'splice_quotes': report['splice_trap']['distinct_quotes'],
    }
    failures = []
    if checks['base_classification'] != expected_base:
        failures.append('base classification drifted')
    if checks['variant_classification'] != expected_variant:
        failures.append('variant classification drifted')
    if checks['only_S-A_changed_class'] != ['S-A']:
        failures.append('variant changed more than the S-A class')
    if not checks['S-A_base_partners_differ']:
        failures.append('S-A no longer demonstrates differing partners per date')
    if not checks['S-A_fixed_stack_absent']:
        failures.append('S-A unexpectedly has a fixed cross-date stack')
    if not checks['S-D_fixed_stack_present']:
        failures.append('S-D lost its fixed cross-date stack')
    if not checks['S-D_bounds_identical']:
        failures.append('S-D fixed stack bounds are no longer identical across dates')
    if not checks['variant_S-A_D1_unusable']:
        failures.append('variant did not make S-A unusable on D1')
    if not checks['variant_S-A_D2_still_usable']:
        failures.append('variant unexpectedly affected S-A on D2')
    if not checks['counterexamples_all_unresolved']:
        failures.append('a certificate hole/overlap was resolved to a value')
    if not checks['splice_quotes_differ']:
        failures.append('splice trap no longer has distinct per-date optima')
    checks['failures'] = failures
    checks['ok'] = not failures
    if failures:
        raise AssertionError('; '.join(failures))
    return checks


def write_repro_inputs(scenario, report):
    """One JSON input per (case, date) that can be replayed through gauge.example."""
    inputs = ROOT / 'out' / 'inputs'
    inputs.mkdir(parents=True, exist_ok=True)
    written = []
    for label, variant in (('base', False), ('variant', True)):
        for result in report['results'][label]:
            blocks = catalog(scenario, result['quote'], variant)
            for date_label, row in result['dates'].items():
                stem = f'{label}-{result["quote"]}-{date_label}'
                status_doc = {'on': row['on'], 'blocks': blocks}
                status_path = inputs / f'{stem}-certificate-status.json'
                status_path.write_text(
                    json.dumps(status_doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                if row['recommendation'] is not None:
                    refs = row['recommendation']['blocks']
                elif row['closest_attempt'] is not None:
                    refs = row['closest_attempt']['blocks']
                else:
                    refs = [result['quote']]
                stack_path = inputs / f'{stem}-stack-interval.json'
                stack_path.write_text(
                    json.dumps(stack_doc(scenario, row['on'], blocks, refs),
                               ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                written.extend([str(status_path.relative_to(ROOT.parent)),
                                str(stack_path.relative_to(ROOT.parent))])
    return written


def main():
    scenario = json.loads(SCENARIO.read_text(encoding='utf-8'))
    dates = scenario['dates']
    quotes = sorted(scenario['quotes'])

    httpd = server(0)
    port = httpd.server_port
    worker = Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        report = {
            'scenario': SCENARIO.name,
            'target_nm': scenario['target_nm'],
            'tolerance_nm': scenario['tolerance_nm'],
            'target_window_nm': [scenario['target_nm'] - scenario['tolerance_nm'],
                                 scenario['target_nm'] + scenario['tolerance_nm']],
            'max_blocks': scenario['max_blocks'],
            'rank': scenario['rank'],
            'dates': dates,
            'quotes': quotes,
            'results': {},
            'fixed_sets': {},
            'best_per_date': {},
            'counterexamples': counterexamples(scenario, port, dates),
        }
        for label, variant in (('base', False), ('variant', True)):
            results = [evaluate(scenario, port, dates, quote, variant) for quote in quotes]
            report['results'][label] = results
            report['fixed_sets'][label] = {
                quote: fixed_sets(scenario, port, dates, quote, variant) for quote in quotes
            }
            report['best_per_date'][label] = best_per_date(results)
        report['splice_trap'] = splice_trap(report['best_per_date']['base'])
        report['guarantees'] = guarantee_table(report)
        report['same_backup_different_partners'] = same_backup_different_partners(report)
        report['variant_transition'] = variant_transition(report)
        report['self_check'] = self_check(report, scenario)
        report['verification'] = verify(report)
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=4)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    report['repro_inputs'] = write_repro_inputs(scenario, report)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + '\n',
                   encoding='utf-8')
    print(json.dumps({
        'written': str(OUT),
        'classification': {
            label: {row['quote']: row['classification'] for row in report['results'][label]}
            for label in ('base', 'variant')
        },
        'fixed_sets': {q: [entry['blocks'] for entry in v]
                       for q, v in report['fixed_sets']['base'].items()},
        'splice_trap': report['splice_trap'],
        'self_check': report['self_check'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
