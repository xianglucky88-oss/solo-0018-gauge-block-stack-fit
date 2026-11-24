"""Plan round-by-round supplementary witness bookings for one fixed stack.

A selected gauge-block combination must be re-verified on the booking day.  Its
current certificate interval crosses the delivery tolerance, so the workbench
plans additional witness measurements before any order is placed:

* an absolute witness constrains the deviation of the combination it actually
  measured (subject or reference);
* a differential witness constrains subject deviation minus reference
  deviation;
* every physical block is one unknown length, including blocks shared by both
  combinations, so shared terms keep a single variable and cancel algebraically
  in differential constraints;
* a booking is not a measurement: only received tickets enter the constraint
  system, every received ticket stays in it, and a reading contradicting the
  existing constraints blocks issuance instead of being discarded.

The constraint system is an integer-coefficient interval system solved exactly
with Fourier-Motzkin projection (``fractions.Fraction`` bounds).
"""
from dataclasses import dataclass
from fractions import Fraction
from math import gcd

from .certificates import number, resolve
from .fit import target

MAX_ROUND_CAP = 4
# Look-ahead enumerates integer readings inside bounded certificate windows.
WINDOW_GUARD = 500
# Defence-in-depth bound on Fourier-Motzkin row growth for pathological inputs.
ROW_GUARD = 4000

KINDS = ('absolute', 'differential')
TARGETS = ('subject', 'reference')


class _Infeasible(Exception):
    pass


class _TooLarge(ValueError):
    pass


def _reduce(coefs, bound):
    """GCD reduction plus infeasibility check; sign is deliberately untouched."""
    divisor = 0
    for value in coefs:
        divisor = gcd(divisor, abs(value))
    if divisor > 1:
        coefs = [value // divisor for value in coefs]
        bound = bound / divisor
    if not any(coefs):
        if bound < 0:
            raise _Infeasible()
        return None
    return tuple(coefs), bound


def _project(rows, widths, eliminate):
    """Fourier-Motzkin eliminate the given column indices.

    Only gcd reduction and infeasibility checks run inside the loop, so row
    signs keep their direction relative to every remaining variable.
    """
    remaining = list(eliminate)
    while remaining:
        pivot = min(remaining, key=lambda k: sum(1 for coefs, _ in rows if coefs[k]))
        positive, negative, zero = [], [], []
        for coefs, bound in rows:
            if coefs[pivot] > 0:
                positive.append((coefs, bound))
            elif coefs[pivot] < 0:
                negative.append((coefs, bound))
            else:
                zero.append((coefs, bound))
        rows = zero
        for p_coefs, p_bound in positive:
            a = p_coefs[pivot]
            for n_coefs, n_bound in negative:
                b = -n_coefs[pivot]
                rows.append(([b * p + a * n for p, n in zip(p_coefs, n_coefs)],
                             b * p_bound + a * n_bound))
        remaining.remove(pivot)
        deduped, seen = [], set()
        for coefs, bound in rows:
            reduced = _reduce(coefs, bound)
            if reduced is not None and reduced not in seen:
                seen.add(reduced)
                deduped.append((list(reduced[0]), reduced[1]))
                if len(deduped) > ROW_GUARD:
                    raise _TooLarge()
        rows = deduped
    return rows


class _System:
    """Rows are integer coefficient vectors with a Fraction upper bound."""

    def __init__(self, variables):
        self.variables = list(variables)
        self.rows = []

    def constrain(self, expr, low, high):
        coefs = [0] * len(self.variables)
        for name, factor in expr.items():
            coefs[self.variables.index(name)] = factor
        self._add(coefs, Fraction(high))
        self._add([-value for value in coefs], Fraction(-low))

    def bound(self, name, low, high):
        self.constrain({name: 1}, low, high)

    def _add(self, coefs, bound):
        reduced = _reduce(coefs, bound)
        if reduced is None:
            return
        if reduced not in self.rows:
            self.rows.append(reduced)
            if len(self.rows) > ROW_GUARD:
                raise _TooLarge()

    def copy(self):
        clone = _System(self.variables)
        clone.rows = list(self.rows)
        return clone

    def feasible(self):
        try:
            _project([([*coefs], bound) for coefs, bound in self.rows],
                     len(self.variables), range(len(self.variables)))
            return True
        except _Infeasible:
            return False

    def range_of(self, expr):
        """Exact [low, high] marginal of a linear expression, or None."""
        width = len(self.variables)
        rows = [([*coefs, 0], bound) for coefs, bound in self.rows]
        base = [0] * width
        for name, factor in expr.items():
            base[self.variables.index(name)] = factor
        rows.append(([-v for v in base] + [1], Fraction(0)))    # z - expr <= 0
        rows.append((base + [-1], Fraction(0)))    # expr - z <= 0
        try:
            rows = _project(rows, width + 1, range(width))
        except _Infeasible:
            return None
        low, high = None, None
        for coefs, bound in rows:
            factor = coefs[width]
            if factor == 0:
                continue
            if factor > 0:                       # factor*z <= bound -> z <= bound/factor
                high = bound / factor if high is None else min(high, bound / factor)
            else:                                # factor*z <= bound -> z >= bound/factor
                value = bound / factor
                low = value if low is None else max(low, value)
        if low is None or high is None:
            return None
        return low, high


@dataclass(frozen=True)
class _Device:
    id: str
    kind: str
    target: str | None
    range_nm: int
    radius_nm: int
    fee: int
    latest_round: int


@dataclass(frozen=True)
class _Ticket:
    id: str
    round_index: int
    device: _Device
    center_nm: int
    scale: str = 'deviation'


def _members(refs, known, label):
    if (not isinstance(refs, list) or not 1 <= len(refs) <= 6 or
            any(not isinstance(x, str) for x in refs) or
            len(set(refs)) != len(refs) or set(refs) - known):
        raise ValueError(label)
    return list(refs)


def _parse_devices(plan, max_rounds, subject_nominal, reference_nominal):
    raw = plan['devices']
    if not isinstance(raw, list) or not 1 <= len(raw) <= 8:
        raise ValueError('witness_plan_devices')
    devices, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('witness_plan_device')
        ident = item.get('id')
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError('witness_plan_device_id')
        seen.add(ident)
        kind = item.get('kind')
        if kind not in KINDS:
            raise ValueError('witness_plan_device_kind')
        target_name = item.get('target')
        if kind == 'absolute':
            if target_name not in TARGETS:
                raise ValueError('witness_plan_device_target')
        elif target_name is not None:
            raise ValueError('witness_plan_differential_target')
        range_nm = number(item.get('range_nm'), 1, 10_000_000_000, 'witness_plan_range')
        radius_nm = number(item.get('radius_nm'), 0, 1_000_000_000, 'witness_plan_radius')
        fee = number(item.get('fee'), 0, 1_000_000_000, 'witness_plan_fee')
        latest = number(item.get('latest_round'), 1, max_rounds, 'witness_plan_latest_round')
        measured_nominal = (max(subject_nominal, reference_nominal) if kind == 'differential'
                            else subject_nominal if target_name == 'subject' else reference_nominal)
        if range_nm < measured_nominal:
            raise ValueError('witness_plan_range_coverage')
        devices.append(_Device(ident, kind, target_name, range_nm, radius_nm, fee, latest))
    return devices


def _parse_tickets(plan, devices, max_rounds):
    raw = plan.get('received', [])
    if not isinstance(raw, list) or len(raw) > max_rounds:
        raise ValueError('witness_plan_received')
    by_id = {device.id: device for device in devices}
    tickets, rounds, ids = [], set(), set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('witness_plan_ticket')
        round_index = number(item.get('round'), 1, max_rounds, 'witness_plan_ticket_round')
        if round_index in rounds:
            raise ValueError('witness_plan_ticket_duplicate_round')
        rounds.add(round_index)
        device = by_id.get(item.get('device'))
        if device is None:
            raise ValueError('witness_plan_ticket_device')
        center = number(item.get('center_nm'), -10_000_000_000, 10_000_000_000,
                        'witness_plan_ticket_center')
        scale = item.get('scale', 'deviation')
        if scale not in ('deviation', 'absolute_length'):
            raise ValueError('witness_plan_ticket_scale')
        if scale == 'absolute_length' and device.kind == 'differential':
            raise ValueError('witness_plan_differential_scale')
        if 'uncertainty_nm' in item and item['uncertainty_nm'] != device.radius_nm:
            raise ValueError('witness_plan_ticket_radius')
        ident = item.get('id')
        if ident is None:
            ident = f'r{round_index}-{device.id}'
        if not isinstance(ident, str) or not ident.strip() or ident in ids:
            raise ValueError('witness_plan_ticket_id')
        ids.add(ident)
        tickets.append(_Ticket(ident, round_index, device, center, scale))
    tickets.sort(key=lambda ticket: ticket.round_index)
    if [ticket.round_index for ticket in tickets] != list(range(1, len(tickets) + 1)):
        raise ValueError('witness_plan_ticket_rounds')
    return tickets


def _ticket_expr(ticket, subject, reference):
    device = ticket.device
    if device.kind == 'differential':
        expr = {name: 1 for name in subject}
        for name in reference:
            expr[name] = expr.get(name, 0) - 1
        return {name: factor for name, factor in expr.items() if factor}
    measured = subject if device.target == 'subject' else reference
    return {name: 1 for name in measured}


def _integral(margin):
    low, high = margin
    lo = -((-low.numerator) // low.denominator) if low.denominator != 1 else int(low)
    hi = high.numerator // high.denominator if high.denominator != 1 else int(high)
    return [lo, hi]


def _state(system, subject, tolerance):
    margin = system.range_of({name: 1 for name in subject})
    if margin is None:
        return None, None
    low, high = _integral(margin)
    if high < -tolerance or low > tolerance:
        state = 'rejectable'
    elif -tolerance <= low and high <= tolerance:
        state = 'deliverable'
    else:
        state = 'undetermined'
    return state, [low, high]


def _enumerate_readings(system, expr, radius):
    margin = system.range_of(expr)
    if margin is None:
        return None
    low, high = _integral(margin)
    centers = list(range(low - radius, high + radius + 1))
    return centers if len(centers) <= WINDOW_GUARD else None


def plan(doc):
    witness_plan = doc.get('witness_plan')
    if witness_plan is None:
        # Optional domain input: datasets without a commission keep using the
        # legacy operations and merely report that no planning is available.
        return {'state': 'no_commission', 'on': doc.get('on')}
    if not isinstance(witness_plan, dict):
        raise ValueError('witness_plan')
    max_rounds = number(witness_plan.get('max_rounds'), 1, MAX_ROUND_CAP, 'witness_plan_max_rounds')
    budget = number(witness_plan.get('budget_fee'), 0, 1_000_000_000, 'witness_plan_budget')

    valid, bad = resolve(doc)
    known = valid.keys() | bad.keys()
    subject = _members(doc['stack'], known, 'witness_plan_subject_members')
    reference = _members(witness_plan.get('reference_stack'), known, 'witness_plan_reference_members')
    unusable = {name: bad[name] for name in sorted(set(subject) | set(reference)) if name in bad}
    if unusable:
        return {'state': 'unresolved_certificate', 'on': doc['on'], 'unusable': unusable,
                'subject_stack': subject, 'reference_stack': reference}

    lower_target, upper_target = target(doc)
    tolerance = doc['tolerance_nm']
    subject_nominal = sum(doc['blocks'][name]['nominal_nm'] for name in subject)
    reference_nominal = sum(doc['blocks'][name]['nominal_nm'] for name in reference)
    devices = _parse_devices(witness_plan, max_rounds, subject_nominal, reference_nominal)
    tickets = _parse_tickets(witness_plan, devices, max_rounds)

    variables = sorted(set(subject) | set(reference))
    nominal = {name: doc['blocks'][name]['nominal_nm'] for name in variables}
    system = _System(variables)
    # Each variable is the signed deviation of one physical block from its
    # nominal length; the certificate centers it with the block uncertainty.
    cert_bounds = {}
    for name in variables:
        uncertainty = valid[name].uncertainty_nm
        cert_bounds[name] = [-uncertainty, uncertainty]
        system.bound(name, -uncertainty, uncertainty)

    subject_cert = [sum(cert_bounds[name][0] for name in subject),
                    sum(cert_bounds[name][1] for name in subject)]
    reference_cert = [sum(cert_bounds[name][0] for name in reference),
                      sum(cert_bounds[name][1] for name in reference)]

    received, spent, conflict = [], 0, None
    for ticket in tickets:
        spent += ticket.device.fee
        expr = _ticket_expr(ticket, subject, reference)
        radius = ticket.device.radius_nm
        # Absolute tickets may be reported as absolute measured lengths; the
        # planner works in deviations, so subtract the measured stack nominal.
        if ticket.device.kind == 'absolute' and ticket.scale == 'absolute_length':
            stack = subject if ticket.device.target == 'subject' else reference
            center = ticket.center_nm - sum(nominal[name] for name in stack)
        else:
            center = ticket.center_nm
        system.constrain(expr, center - radius, center + radius)
        if not system.feasible():
            conflict = {'ticket': ticket.id, 'reason': 'reading_contradicts_constraints'}
            break
        measured_names = (subject if ticket.device.kind == 'differential'
                          or ticket.device.target == 'subject' else reference)
        received.append({'id': ticket.id, 'round': ticket.round_index, 'device': ticket.device.id,
                         'kind': ticket.device.kind, 'target': ticket.device.target,
                         'interval_nm': [center - radius, center + radius],
                         'certificates': {name: valid[name].certificate for name in measured_names}})
    if spent > budget:
        return {'state': 'budget_exceeded', 'on': doc['on'], 'spent_fee': spent, 'budget_fee': budget,
                'subject_stack': subject, 'reference_stack': reference, 'received': received}
    if conflict is not None:
        return {'state': 'witness_conflict', 'on': doc['on'], 'conflict': conflict,
                'subject_stack': subject, 'reference_stack': reference, 'received': received,
                'certificate_bounds_nm': {'subject': subject_cert, 'reference': reference_cert}}

    state, feasible_x = _state(system, subject, tolerance)
    feasible_y = _integral(system.range_of({name: 1 for name in reference}))
    d_expr = {name: 1 for name in subject}
    for name in reference:
        d_expr[name] = d_expr.get(name, 0) - 1
    d_expr = {name: factor for name, factor in d_expr.items() if factor}
    feasible_d = _integral(system.range_of(d_expr))
    # Per-block deviation margins make the single-unknown identity observable:
    # a shared block keeps one interval, never two independent extremes.
    block_margins = {name: _integral(system.range_of({name: 1})) for name in variables}

    last_round = len(received)
    next_round = last_round + 1
    remaining_budget = budget - spent
    rounds_left = max_rounds - last_round

    def option_record(device):
        reasons = []
        if next_round > device.latest_round:
            reasons.append('past_latest_round')
        if device.fee > remaining_budget:
            reasons.append('over_remaining_budget')
        bookable = not reasons
        record = {'device': device.id, 'kind': device.kind, 'target': device.target,
                  'fee': device.fee, 'radius_nm': device.radius_nm, 'latest_round': device.latest_round,
                  'bookable': bookable, 'blocked_reason': reasons,
                  'conclusive_within_remaining_rounds': None}
        if bookable:
            record['conclusive_within_remaining_rounds'] = _conclusive(
                system, device, subject, reference, tolerance, rounds_left, remaining_budget)
        return record

    if state in ('deliverable', 'rejectable'):
        booking, stop_reason = None, state
    elif next_round > max_rounds:
        booking, stop_reason = None, 'rounds_exhausted'
    else:
        options = [option_record(device) for device in devices]
        bookable_options = [row for row in options if row['bookable']]
        if not bookable_options:
            booking, stop_reason = {'round': next_round, 'options': options,
                                    'recommended': None}, 'no_bookable_device'
        else:
            # The next order is chosen by fee; the conclusive flag tells whether
            # the booking guarantees a final answer before the cap is reached.
            recommended = sorted(bookable_options,
                                 key=lambda row: (row['fee'], row['device']))[0]
            booking = {'round': next_round, 'options': options,
                       'recommended': recommended['device']}
            stop_reason = None

    strategies = _strategies(system, devices, subject, reference, tolerance, max_rounds, budget)

    return {
        'state': state,
        'on': doc['on'],
        'subject_stack': subject,
        'reference_stack': reference,
        'shared_blocks': sorted(set(subject) & set(reference)),
        'block_margins_nm': block_margins,
        'subject': {'nominal_nm': subject_nominal,
                    'certificate_bounds_nm': subject_cert,
                    'delivery_limits_nm': [lower_target - subject_nominal,
                                           upper_target - subject_nominal],
                    'feasible_nm': feasible_x,
                    'certificates': {name: valid[name].certificate for name in subject}},
        'reference': {'nominal_nm': reference_nominal,
                      'certificate_bounds_nm': reference_cert,
                      'feasible_nm': feasible_y,
                      'certificates': {name: valid[name].certificate for name in reference}},
        'difference_nm': feasible_d,
        'rounds': {'max': max_rounds, 'last_received': last_round, 'next': next_round,
                   'remaining': rounds_left},
        'budget': {'limit': budget, 'spent': spent, 'remaining': remaining_budget},
        'received': received,
        'booking': booking,
        'stop_reason': stop_reason,
        'strategies': strategies,
        'recommended_strategy': _recommend(strategies),
        'decision': {'state': state, 'deliverable': state == 'deliverable',
                     'rejectable': state == 'rejectable',
                     'undetermined': state == 'undetermined',
                     'basis_ticket_ids': [row['id'] for row in received]},
    }


def _conclusive(system, device, subject, reference, tolerance, rounds_left, budget_left):
    """Whether every feasible reading of this device still ends in a decision."""
    if rounds_left <= 0 or device.fee > budget_left:
        return False
    expr = _ticket_expr(_Ticket('probe', 1, device, 0), subject, reference)
    centers = _enumerate_readings(system, expr, device.radius_nm)
    if centers is None:
        return None
    for center in centers:
        probe = system.copy()
        probe.constrain(expr, center - device.radius_nm, center + device.radius_nm)
        state, _ = _state(probe, subject, tolerance)
        if state != 'deliverable' and state != 'rejectable':
            return False
    return True


def _strategies(system, devices, subject, reference, tolerance, max_rounds, budget):
    def first_choices(predicate):
        return sorted((device for device in devices
                       if predicate(device) and device.latest_round >= 1 and device.fee <= budget),
                      key=lambda device: (device.fee, device.id))

    absolute = first_choices(lambda d: d.kind == 'absolute' and d.target == 'subject')
    differential = first_choices(lambda d: d.kind == 'differential')

    def worst_case(first, allowed):
        if first is None:
            return {'bookable_now': False, 'blocked_reason': 'no_round_one_device',
                    'first_round_device': None, 'first_round_fee': None, 'guaranteed': None,
                    'worst_case_fee': None, 'worst_case_round': None}
        expr = _ticket_expr(_Ticket('probe', 1, first, 0), subject, reference)
        centers = _enumerate_readings(system, expr, first.radius_nm)
        if centers is None:
            return {'bookable_now': True, 'first_round_device': first.id,
                    'first_round_fee': first.fee, 'guaranteed': None,
                    'worst_case_fee': None, 'worst_case_round': None,
                    'blocked_reason': 'analysis_window_exceeded'}
        guaranteed, worst_fee, worst_round = True, first.fee, 1
        for center in centers:
            probe = system.copy()
            probe.constrain(expr, center - first.radius_nm, center + first.radius_nm)
            state, _ = _state(probe, subject, tolerance)
            if state in ('deliverable', 'rejectable'):
                continue
            continuation = _continuation(probe, allowed, subject, reference, tolerance,
                                         max_rounds - 1, budget - first.fee, 2)
            if continuation is None:
                guaranteed = False
                break
            tail_fee, round_index = continuation
            worst_fee = max(worst_fee, first.fee + tail_fee)
            worst_round = max(worst_round, round_index)
        return {'bookable_now': True, 'first_round_device': first.id,
                'first_round_fee': first.fee, 'guaranteed': guaranteed,
                'worst_case_fee': worst_fee if guaranteed else None,
                'worst_case_round': worst_round if guaranteed else None}

    first_abs = absolute[0] if absolute else None
    first_diff = differential[0] if differential else None
    followup_pool = [device for device in devices if device.latest_round >= 1]
    return [
        {'id': 'absolute_first', **worst_case(first_abs, absolute)},
        {'id': 'differential_then_followup', **worst_case(first_diff, followup_pool)},
    ]


def _continuation(system, devices, subject, reference, tolerance, rounds_left, budget_left, round_index):
    state, _ = _state(system, subject, tolerance)
    if state in ('deliverable', 'rejectable'):
        return 0, round_index - 1
    if rounds_left <= 0:
        return None
    options = sorted((device for device in devices
                      if device.latest_round >= round_index and device.fee <= budget_left),
                     key=lambda device: (device.fee, device.id))
    for device in options:
        expr = _ticket_expr(_Ticket('probe', round_index, device, 0), subject, reference)
        centers = _enumerate_readings(system, expr, device.radius_nm)
        if centers is None:
            return None
        branches = []
        for center in centers:
            probe = system.copy()
            probe.constrain(expr, center - device.radius_nm, center + device.radius_nm)
            tail = _continuation(probe, devices, subject, reference, tolerance,
                                 rounds_left - 1, budget_left - device.fee, round_index + 1)
            if tail is None:
                branches = None
                break
            branches.append((device.fee + tail[0], tail[1]))
        if branches is not None:
            return max(fee for fee, _ in branches), max(round_no for _, round_no in branches)
    return None


def _recommend(strategies):
    guaranteed = [row for row in strategies if row.get('guaranteed') is True]
    if not guaranteed:
        return None
    return sorted(guaranteed,
                  key=lambda row: (row['first_round_fee'], row['worst_case_fee'], row['id']))[0]['id']
