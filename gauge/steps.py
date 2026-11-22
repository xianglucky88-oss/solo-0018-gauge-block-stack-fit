"""Cumulative step stacks: one pile of blocks forms several measured heights.

Blocks added for a lower step stay in the pile for every higher step, so the
height measured at level k is the sum of every block added at levels 1..k.
All levels are judged against one certificate resolution for the request day.
"""
from copy import deepcopy
from itertools import combinations
from .certificates import number, resolve
from .fit import target

BIG = 1 << 62


def targets(doc):
    raw = doc.get('targets')
    if not isinstance(raw, list) or not 2 <= len(raw) <= 4:
        raise ValueError('targets')
    spans = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('targets')
        spans.append(target(item))
    for (low1, high1), (low2, high2) in zip(spans, spans[1:]):
        if not low1 < low2 or not high1 < high2:
            raise ValueError('targets_not_increasing')
    return spans


def min_new(doc, count):
    raw = doc.get('min_new_per_level')
    if type(raw) is int:
        per = [raw] * count
    elif isinstance(raw, list) and len(raw) == count:
        per = raw
    else:
        raise ValueError('min_new_per_level')
    if any(type(x) is not int or x < 1 for x in per):
        raise ValueError('min_new_per_level')
    return per


def build(doc):
    good, bad = resolve(doc)
    spans = targets(doc)
    max_blocks = number(doc.get('max_blocks'), 1, 6, 'max_blocks')
    per = min_new(doc, len(spans))
    if sum(per) > max_blocks:
        raise ValueError('min_new_per_level')
    return Planner(good, spans, max_blocks, per), good, bad


class Planner:
    """Search nested block sets under one certificate resolution."""

    def __init__(self, good, spans, max_blocks, per_level):
        self.names = sorted(good)
        self.center = [good[x].center_nm for x in self.names]
        self.radius = [good[x].uncertainty_nm for x in self.names]
        self.spans = spans
        self.levels = len(spans)
        self.max_blocks = max_blocks
        self.per_level = per_level
        self.suffix = [0] * (self.levels + 1)
        for k in range(self.levels - 1, -1, -1):
            self.suffix[k] = self.suffix[k + 1] + per_level[k]

    def margin(self, level, center, radius):
        low, high = self.spans[level]
        return min(center - radius - low, high - center - radius)

    def _remaining(self, mask):
        return [i for i in range(len(self.names)) if not mask >> i & 1]

    def _mask(self, combo):
        bits = 0
        for i in combo:
            bits |= 1 << i
        return bits

    def _room(self, level, upto, used):
        return self.max_blocks - (self.suffix[level + 1] - self.suffix[upto]) - used

    def _hopeless(self, level, remaining, center, radius, need, room):
        if room < need or len(remaining) < need:
            return True
        low, high = self.spans[level]
        gain = sorted((self.center[i] + self.radius[i] for i in remaining), reverse=True)
        if center + radius + sum(gain[:room]) < low:
            return True
        drop = sorted(self.center[i] - self.radius[i] for i in remaining)
        return center - radius + sum(drop[:need]) > high

    def _combos(self, remaining, need, room, skip_late=-1):
        top = min(room, len(remaining))
        pool, late = remaining, False
        if skip_late in remaining:
            pool = [i for i in remaining if i != skip_late]
            late = True
        for size in range(need, top + 1):
            for combo in combinations(pool, size):
                yield combo
            if late:
                for combo in combinations(pool, size - 1):
                    yield combo + (skip_late,)

    def solve(self):
        """Best full card: max worst-level margin, then fewest blocks, then stable key."""
        best = []

        def dfs(level, mask, used, center, radius, worst, rows):
            if level == self.levels:
                key = (-worst, used, tuple(row[0] for row in rows))
                if not best or key < best[0]:
                    best[:] = [key, list(rows)]
                return
            if best and (worst < -best[0][0] or (worst == -best[0][0] and used >= best[0][1])):
                return
            remaining = self._remaining(mask)
            need = self.per_level[level]
            room = self._room(level, self.levels, used)
            if self._hopeless(level, remaining, center, radius, need, room):
                return
            for combo in self._combos(remaining, need, room):
                c2 = center + sum(self.center[i] for i in combo)
                r2 = radius + sum(self.radius[i] for i in combo)
                margin = self.margin(level, c2, r2)
                if margin < 0:
                    continue
                rows.append((tuple(self.names[i] for i in combo), c2, r2, margin))
                dfs(level + 1, mask | self._mask(combo), used + len(combo), c2, r2,
                    min(worst, margin), rows)
                rows.pop()

        dfs(0, 0, 0, 0, 0, BIG, [])
        return best[1] if best else None

    def exists(self, upto):
        """Whether some chain satisfies the first `upto` levels."""
        found = []

        def dfs(level, mask, used, center, radius):
            if found:
                return
            if level == upto:
                found.append(True)
                return
            remaining = self._remaining(mask)
            need = self.per_level[level]
            room = self._room(level, upto, used)
            if self._hopeless(level, remaining, center, radius, need, room):
                return
            for combo in self._combos(remaining, need, room):
                c2 = center + sum(self.center[i] for i in combo)
                r2 = radius + sum(self.radius[i] for i in combo)
                if self.margin(level, c2, r2) < 0:
                    continue
                dfs(level + 1, mask | self._mask(combo), used + len(combo), c2, r2)

        dfs(0, 0, 0, 0, 0)
        return bool(found)

    def solo_best(self, level):
        """Highest-margin set for one level alone, regardless of other levels."""
        best = None
        n = len(self.names)
        for size in range(1, min(self.max_blocks, n) + 1):
            for combo in combinations(range(n), size):
                c = sum(self.center[i] for i in combo)
                r = sum(self.radius[i] for i in combo)
                margin = self.margin(level, c, r)
                key = (-margin, size, tuple(self.names[i] for i in combo))
                if best is None or key < best[0]:
                    best = (key, combo, c, r, margin)
        if best is None:
            return None
        _, combo, c, r, margin = best
        return {'blocks': [self.names[i] for i in combo], 'center_nm': c,
                'uncertainty_nm': r, 'bounds_nm': [c - r, c + r], 'margin_nm': margin}

    def solo_stats(self, level):
        """Per-block solo feasibility data: within-set counts and best margins."""
        n = len(self.names)
        total_within, containing, best_margin = 0, [0] * n, [None] * n
        for size in range(1, min(self.max_blocks, n) + 1):
            for combo in combinations(range(n), size):
                c = sum(self.center[i] for i in combo)
                r = sum(self.radius[i] for i in combo)
                margin = self.margin(level, c, r)
                if margin >= 0:
                    total_within += 1
                    for i in combo:
                        containing[i] += 1
                for i in combo:
                    if best_margin[i] is None or margin > best_margin[i]:
                        best_margin[i] = margin
        return total_within, containing, best_margin

    def chain_threshold(self, block):
        """Largest certificate radius for `block` that still allows a full chain.

        Returns None when a chain avoiding the block exists, so the block
        cannot break the assembly on its own.
        """
        best, free = [], []

        def dfs(level, mask, used, center, radius, seen, worst_seen):
            if free:
                return
            if level == self.levels:
                if not seen:
                    free.append(True)
                elif not best or worst_seen > best[0]:
                    best[:] = [worst_seen]
                return
            if best and seen and worst_seen <= best[0]:
                return
            remaining = self._remaining(mask)
            need = self.per_level[level]
            room = self._room(level, self.levels, used)
            if self._hopeless(level, remaining, center, radius, need, room):
                return
            for combo in self._combos(remaining, need, room, skip_late=block):
                c2 = center + sum(self.center[i] for i in combo)
                r2 = radius + sum(self.radius[i] for i in combo)
                margin = self.margin(level, c2, r2)
                if margin < 0:
                    continue
                seen2 = seen or block in combo
                dfs(level + 1, mask | self._mask(combo), used + len(combo), c2, r2,
                    seen2, min(worst_seen, margin) if seen2 else worst_seen)

        dfs(0, 0, 0, 0, 0, False, BIG)
        if free or not best:
            return None
        return self.radius[block] + best[0]

    def reachable(self, upto):
        """Cumulative stacks after `upto` levels; each mask keeps its best card key."""
        states = {0: ((), 0, 0, 0)}
        for level in range(upto):
            nxt = {}
            for mask, (key, used, center, radius) in states.items():
                remaining = self._remaining(mask)
                need = self.per_level[level]
                room = self._room(level, upto, used)
                for combo in self._combos(remaining, need, room):
                    c2 = center + sum(self.center[i] for i in combo)
                    r2 = radius + sum(self.radius[i] for i in combo)
                    if self.margin(level, c2, r2) < 0:
                        continue
                    m2 = mask | self._mask(combo)
                    k2 = key + (tuple(self.names[i] for i in combo),)
                    if m2 not in nxt or k2 < nxt[m2][0]:
                        nxt[m2] = (k2, used + len(combo), c2, r2)
            states = nxt
        return states

    def limit_evidence(self, prefix):
        """Why level `prefix` + 1 cannot follow any feasible prefix chain."""
        states = self.reachable(prefix)
        low, high = self.spans[prefix]
        need = self.per_level[prefix]
        best, extensions, most_room = None, 0, 0
        for mask in sorted(states, key=lambda m: states[m][0]):
            key, used, center, radius = states[mask]
            remaining = self._remaining(mask)
            room = min(self.max_blocks - used, len(remaining))
            most_room = max(most_room, room)
            for combo in self._combos(remaining, need, room):
                c2 = center + sum(self.center[i] for i in combo)
                r2 = radius + sum(self.radius[i] for i in combo)
                margin = min(c2 - r2 - low, high - c2 - r2)
                extensions += 1
                ekey = (-margin, len(combo), key + (tuple(self.names[i] for i in combo),))
                if best is None or ekey < best[0]:
                    best = (ekey, mask, combo, c2, r2, margin)
        out = {'feasible_prefixes': len(states), 'next_min_new_blocks': need}
        if not extensions:
            out['reason'] = 'no_blocks_left'
            out['most_blocks_available'] = most_room
            out['max_blocks'] = self.max_blocks
            return out
        out['reason'] = 'target_missed'
        out['extensions_considered'] = extensions
        _, mask, combo, c2, r2, margin = best
        out['closest'] = {
            'prefix_stack': [self.names[i] for i in range(len(self.names)) if mask >> i & 1],
            'add': [self.names[i] for i in combo],
            'bounds_nm': [c2 - r2, c2 + r2],
            'margin_nm': margin,
            'short_below_nm': max(0, low - (c2 - r2)),
            'over_above_nm': max(0, (c2 + r2) - high),
        }
        return out

    def diagnose(self):
        """Explain why no full card exists, without stitching per-level winners."""
        for level in range(self.levels):
            solo = self.solo_best(level)
            if solo is None or solo['margin_nm'] < 0:
                low, high = self.spans[level]
                closest = None
                if solo is not None:
                    closest = dict(solo)
                    closest['short_below_nm'] = max(0, low - solo['bounds_nm'][0])
                    closest['over_above_nm'] = max(0, solo['bounds_nm'][1] - high)
                return {'state': 'level_unreachable', 'level': level + 1,
                        'target_nm': [low, high], 'closest': closest}
        prefix = 0
        while prefix < self.levels and self.exists(prefix + 1):
            prefix += 1
        low, high = self.spans[prefix]
        return {'state': 'broken_chain', 'longest_prefix': prefix,
                'next_level': prefix + 1, 'next_target_nm': [low, high],
                'limit': self.limit_evidence(prefix)}

    def render(self, rows):
        """Assembler view of a solved card: per-level adds and cumulative intervals."""
        levels, stack = [], []
        for level, (names, center, radius, margin) in enumerate(rows, 1):
            stack = sorted(stack + list(names))
            low, high = self.spans[level - 1]
            levels.append({'level': level, 'add': list(names), 'stack': stack,
                           'center_nm': center, 'uncertainty_nm': radius,
                           'bounds_nm': [center - radius, center + radius],
                           'target_nm': [low, high], 'margin_nm': margin,
                           'state': 'within'})
        return levels


def card_of(plan, good, rows):
    used = sorted(x for names, *_ in rows for x in names)
    return {'worst_margin_nm': min(row[3] for row in rows),
            'total_blocks': len(used),
            'levels': plan.render(rows),
            'evidence': {x: good[x].certificate for x in used}}


def step_card(doc):
    plan, good, bad = build(doc)
    rows = plan.solve()
    if rows is None:
        out = plan.diagnose()
        out['unusable'] = bad
        return out
    return {'state': 'matched', **card_of(plan, good, rows), 'unusable': bad}


def _rewrite(doc, name, new_radius):
    modified = deepcopy(doc)
    when = doc['on']
    for cert in modified['blocks'][name]['certificates']:
        if cert['from'] <= when < cert['until']:
            old = cert['uncertainty_nm']
            cert['uncertainty_nm'] = new_radius
            return {'block': name, 'certificate': cert['id'],
                    'uncertainty_nm': {'from': old, 'to': new_radius}}, modified
    raise ValueError('certificate_window')


def step_counterexample(doc):
    """One legal certificate-radius change that keeps every level reachable
    alone yet makes the full stack impossible; only recommendation and
    breakpoint evidence are returned."""
    plan, good, bad = build(doc)
    rows = plan.solve()
    if rows is None:
        diagnosis = plan.diagnose()
        diagnosis['unusable'] = bad
        return {'state': 'baseline_not_assemblable', 'diagnosis': diagnosis}
    recommendation = card_of(plan, good, rows)
    recommendation['unusable'] = bad
    stats = [plan.solo_stats(k) for k in range(plan.levels)]
    for index, name in enumerate(plan.names):
        old = plan.radius[index]
        allow = BIG
        for k in range(plan.levels):
            total_within, containing, best_margin = stats[k]
            if containing[index] < total_within:
                continue
            allow = min(allow, old + best_margin[index])
        threshold = plan.chain_threshold(index)
        if threshold is None:
            continue
        new_radius = threshold + 1
        if new_radius > min(allow, plan.center[index] - 1):
            continue
        change, modified = _rewrite(doc, name, new_radius)
        good2, _ = resolve(modified)
        replay = Planner(good2, plan.spans, plan.max_blocks, plan.per_level)
        if replay.solve() is not None:
            continue
        solo = [replay.solo_best(k) for k in range(replay.levels)]
        if any(row is None or row['margin_nm'] < 0 for row in solo):
            continue
        diagnosis = replay.diagnose()
        if diagnosis['state'] != 'broken_chain':
            continue
        return {'state': 'counterexample_found', 'change': change,
                'recommendation': recommendation,
                'modified': {'solo': solo,
                             'longest_prefix': diagnosis['longest_prefix'],
                             'next_level': diagnosis['next_level'],
                             'next_target_nm': diagnosis['next_target_nm'],
                             'limit': diagnosis['limit']}}
    return {'state': 'no_single_block_counterexample',
            'blocks_checked': len(plan.names)}
