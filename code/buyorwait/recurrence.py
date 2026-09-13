"""Recurring series detection and projection (plan §4.3, Q9)."""
from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Optional

from . import vocabulary as roles
from .config import Switches
from .ledger import Flow

MONTHLY = "monthly"
REGULAR_SHARE = 0.75
MIN_OCCURRENCES = 3
RECENT = 6

_INCOME_ACTIVE = {roles.RECURRING, roles.INCOME_STARTS, roles.INCOME_RESUME}
_INCOME_BOUNDARY = {roles.INCOME_ENDS, roles.INCOME_PAUSE, roles.INCOME_ENDED_STREAM}


@dataclass(frozen=True)
class Series:
    key: tuple[str, ...]          # (category, direction) or (category, direction, description) when split
    category: str
    direction: str
    cadence: object               # MONTHLY or a step in days
    day_of_month: Optional[int]
    last_date: date
    raw_amount: float             # in `currency`
    currency: str
    flexibility: str              # of the latest occurrence
    minimum_allowed: Optional[float]
    occurrences: int


def nearest_rank(values: list[float], q: float) -> float:
    """Percentile that always returns an observed value."""
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(q * len(ordered) + 0.5)) - 1))
    return ordered[index]


def cadence_of(flows: list[Flow]) -> tuple[object, Optional[int]]:
    dates = sorted(f.date for f in flows)
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if not gaps:
        return None, None
    monthly = sum(1 for g in gaps if 28 <= g <= 31)
    if monthly >= REGULAR_SHARE * len(gaps):
        days = Counter(d.day for d in dates).most_common()
        top = days[0][1]
        day = max(d for d, c in days if c == top) if len(days) > 1 else days[0][0]
        return MONTHLY, day
    gap, count = Counter(gaps).most_common(1)[0]
    if count >= REGULAR_SHARE * len(gaps) and gap > 0:
        return gap, None
    day, same = Counter(d.day for d in dates).most_common(1)[0]
    if len(dates) >= 3 and same >= 0.8 * len(dates) and all(g >= 27 for g in gaps):
        return MONTHLY, day  # monthly on a fixed day with a gap (e.g. unpaid leave)
    return None, None


def _series(key, flows: list[Flow], amount: float, cadence, day) -> Series:
    flows = sorted(flows, key=lambda f: f.date)
    last = flows[-1]
    return Series(
        key=key, category=last.category, direction=last.direction, cadence=cadence, day_of_month=day,
        last_date=last.date, raw_amount=amount, currency=last.currency, flexibility=last.flexibility,
        minimum_allowed=last.minimum_allowed, occurrences=len(flows),
    )


def estimate(values: list[float], estimator: str) -> float:
    if estimator == "last":
        return values[-1]
    if estimator == "mean":
        return sum(values) / len(values)
    if estimator == "max":
        return max(values)
    quantile = {"median": 0.5, "p75": 0.75, "p90": 0.9}[estimator]
    return nearest_rank(values, quantile)


def _expense_amount(flows: list[Flow], switches: Switches) -> float:
    recent = [f.raw_amount for f in sorted(flows, key=lambda f: f.date)[-switches.recent_occurrences:]]
    return estimate(recent, switches.expense_estimator)


def _income_amount(flows: list[Flow], switches: Switches) -> float:
    recent = [f.raw_amount for f in sorted(flows, key=lambda f: f.date)[-switches.recent_occurrences:]]
    return nearest_rank(recent, switches.income_percentile)


def _active_income_rows(rows: list[Flow]) -> list[Flow]:
    """Rows of the current stream segment; empty when the latest lifecycle marker ended or paused it."""
    rows = sorted(rows, key=lambda f: f.date)
    if rows and rows[-1].role in _INCOME_BOUNDARY:
        return []  # final payroll, old employer, or leave with no return yet
    boundary = -1
    for i, f in enumerate(rows):
        if f.role in (roles.INCOME_ENDS, roles.INCOME_ENDED_STREAM):
            boundary = i
    return [f for f in rows[boundary + 1:] if f.role in _INCOME_ACTIVE or f.role == roles.INCOME_PAUSE]


def day_clusters(flows: list[Flow], tolerance: int = 3) -> list[list[Flow]]:
    """Group rows paid on the same day of the month (±tolerance), e.g. the 7th and the 20th."""
    clusters: list[tuple[int, list[Flow]]] = []
    for f in sorted(flows, key=lambda f: f.date.day):
        for i, (anchor, members) in enumerate(clusters):
            if abs(f.date.day - anchor) <= tolerance:
                members.append(f)
                break
        else:
            clusters.append((f.date.day, [f]))
    return [sorted(members, key=lambda f: f.date) for _, members in clusters]


def _stale(series: Series, history_end: date) -> bool:
    """An income series that already missed an expected payment before the ledger ends has stopped."""
    grace = 5
    if series.cadence == MONTHLY:
        nxt = occurrence_dates(series, series.last_date + timedelta(days=1), series.last_date + timedelta(days=45))
        return bool(nxt) and nxt[0] + timedelta(days=grace) < history_end
    return series.last_date + timedelta(days=int(series.cadence) + grace) < history_end


def _income_series(key_prefix: tuple[str, ...], rows: list[Flow], need: int, amount_fn) -> list[Series]:
    cadence, day = cadence_of(rows)
    if len(rows) >= need and cadence is not None:
        return [_series(key_prefix, rows, amount_fn(rows), cadence, day)]
    out = []
    for cluster in day_clusters(rows):
        cadence, day = cadence_of(cluster)
        if len(cluster) >= need and cadence == MONTHLY:
            out.append(_series(key_prefix + (f"day{day}",), cluster, amount_fn(cluster), cadence, day))
    if out:
        return out
    by_description: dict[str, list[Flow]] = defaultdict(list)
    for f in rows:
        by_description[f.description].append(f)
    for description, sub in by_description.items():
        cadence, day = cadence_of(sub)
        if len(sub) >= need and cadence is not None:
            out.append(_series(key_prefix + (description,), sub, amount_fn(sub), cadence, day))
    return out


def detect_series(history: list[Flow], switches: Switches, confirmed: set[tuple[str, str]],
                  unconfirmed_variable: frozenset[str] = frozenset()) -> list[Series]:
    out: list[Series] = []
    expenses: dict[str, list[Flow]] = defaultdict(list)
    incomes: dict[str, list[Flow]] = defaultdict(list)
    variable: dict[str, list[Flow]] = defaultdict(list)
    for f in history:
        if f.direction == "debit" and f.role == roles.RECURRING:
            expenses[f.category].append(f)
        elif f.direction == "credit" and (f.role in _INCOME_ACTIVE or f.role in _INCOME_BOUNDARY):
            incomes[f.category].append(f)
        elif f.direction == "credit" and f.role == roles.VARIABLE_INCOME:
            variable[f.category].append(f)

    for category, flows in expenses.items():
        cadence, day = cadence_of(flows)
        if len(flows) >= MIN_OCCURRENCES and cadence is not None:
            out.append(_series((category, "debit"), flows, _expense_amount(flows, switches), cadence, day))
        elif len(flows) >= MIN_OCCURRENCES:  # irregular expense: never under-project, use median gap
            dates = sorted(f.date for f in flows)
            gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
            out.append(_series((category, "debit"), flows, _expense_amount(flows, switches), max(1, gaps[len(gaps) // 2]), None))

    history_end = max((f.date for f in history), default=date.min)
    income_out: list[Series] = []
    for category, rows in incomes.items():
        active = _active_income_rows(rows)
        need = 2 if (category, "credit") in confirmed else MIN_OCCURRENCES
        if len(active) >= need:
            income_out += _income_series((category, "credit"), active, need, lambda r: _income_amount(r, switches))

    if switches.variable_income == "low_percentile":
        def low(rows: list[Flow]) -> float:
            recent = [f.raw_amount for f in sorted(rows, key=lambda f: f.date)[-switches.recent_occurrences:]]
            return nearest_rank(recent, switches.income_percentile)
        for category, flows in variable.items():
            if category in unconfirmed_variable:
                continue  # a message says this payout is pending / not withdrawable
            income_out += _income_series((category, "credit", "variable"), flows, MIN_OCCURRENCES, low)
    out += [s for s in income_out if not _stale(s, history_end)]
    return out


def occurrence_dates(series: Series, start: date, end: date) -> list[date]:
    dates: list[date] = []
    if series.cadence == MONTHLY:
        year, month = start.year, start.month
        while True:
            last_day = calendar.monthrange(year, month)[1]
            d = date(year, month, min(series.day_of_month, last_day))
            if d > end:
                break
            if d >= start and d > series.last_date:
                dates.append(d)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    else:
        step = timedelta(days=int(series.cadence))
        d = series.last_date + step
        while d <= end:
            if d >= start:
                dates.append(d)
            d += step
    return dates


def half_cadence(series: Series) -> int:
    return 15 if series.cadence == MONTHLY else max(1, int(series.cadence) // 2)
