"""90-day balance simulation: projected + known + evidence flows, low point, safe amount, earliest date (plan §5.1)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Iterable, Optional

from . import vocabulary as roles
from .config import FORECAST_DAYS, Switches
from .fx import FxTable
from .ledger import Flow, UserLedger
from .recurrence import Series, detect_series, half_cadence, occurrence_dates

EPS = 1e-6


@dataclass(frozen=True)
class Change:
    kind: str                 # stop | reduce
    category: str
    target_event_id: str
    new_raw_amount: Optional[float] = None


def _parse_date(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def confirmed_series(ledger: UserLedger, effects: list[dict]) -> set[tuple[str, str]]:
    out = {(f.category, f.direction) for f in ledger.known if f.direction == "credit" and f.role == roles.KNOWN_FUTURE}
    out |= {(e["category"], e["direction"]) for e in effects if e["type"] in ("series_starts", "confirmed_credit", "temporary_amount", "occurrence_moved", "series_amount_change")}
    return out


class Forecast:
    def __init__(self, ledger: UserLedger, fx: FxTable, switches: Switches, effects: list[dict]):
        self.ledger = ledger
        self.fx = fx
        self.switches = switches
        self.start = ledger.request.request_date
        self.end = self.start + timedelta(days=switches.window_days)
        self.home = ledger.profile.home_currency
        variable_categories = {f.category for f in ledger.history if f.role == roles.VARIABLE_INCOME}
        unconfirmed_variable = frozenset(e["category"] for e in effects if e["type"] == "not_confirmed" and e["direction"] == "credit" and e["category"] in variable_categories)
        self.series = detect_series(ledger.history, switches, confirmed_series(ledger, effects), unconfirmed_variable)
        self.flows = self._build_flows(effects)

    # ---- flow construction -------------------------------------------------
    def _convert(self, raw: float, currency: Optional[str], on: date) -> float:
        return self.fx.convert(raw, currency or self.home, self.home, on)

    def _projected(self) -> list[Flow]:
        out = []
        first = self.start + timedelta(days=self.switches.projection_offset)
        for s in self.series:
            for d in occurrence_dates(s, first, self.end):
                out.append(Flow(
                    date=d, amount=self._convert(s.raw_amount, s.currency, d), raw_amount=s.raw_amount, currency=s.currency,
                    direction=s.direction, category=s.category, description="projected", role=roles.RECURRING,
                    source="projected", flexibility=s.flexibility, minimum_allowed=s.minimum_allowed, series_key=s.key,
                ))
        return out

    @staticmethod
    def _nearest(flows: list[Flow], category: str, direction: str, on: date, within: int, sources: Iterable[str]) -> Optional[int]:
        best = None
        for i, f in enumerate(flows):
            if f.category == category and f.direction == direction and f.source in sources:
                gap = abs((f.date - on).days)
                if gap <= within and (best is None or gap < best[0]):
                    best = (gap, i)
        return None if best is None else best[1]

    def _series_window(self, category: str, direction: str) -> int:
        spans = [half_cadence(s) for s in self.series if s.category == category and s.direction == direction]
        return max(spans) if spans else 15

    def _build_flows(self, effects: list[dict]) -> list[Flow]:
        flows = self._projected()
        # known scheduled occurrences replace the projected occurrence of the same series in the same cycle
        for k in self.ledger.known:
            if k.role == roles.KNOWN_FUTURE:
                i = self._nearest(flows, k.category, k.direction, k.date, self._series_window(k.category, k.direction), ("projected",))
                if i is not None:
                    flows.pop(i)
            flows.append(k)
        flows = self._apply_effects(flows, effects)
        if not self.switches.pending_in_balance:
            flows.extend(replace(p, date=self.start) for p in self.ledger.pending)
        return sorted((f for f in flows if self.start <= f.date <= self.end), key=lambda f: (f.date, f.direction))

    def _apply_effects(self, flows: list[Flow], effects: list[dict]) -> list[Flow]:
        by_message: dict[str, list[dict]] = {}
        for e in effects:
            by_message.setdefault(e["message_id"], []).append(e)
        for e in effects:
            kind, cat, direction = e["type"], e["category"], e["direction"]
            on = _parse_date(e.get("date"))
            begin = max(on, self.start) if on else self.start
            amount, currency, percent = e.get("amount"), e.get("currency"), e.get("percent")

            def matches(f: Flow) -> bool:
                return f.category == cat and f.direction == direction and f.source == "projected"

            if kind == "series_ends":
                remaining = any(o["type"] == "series_amount_change" and o["category"] == cat for o in by_message[e["message_id"]])
                if not remaining:
                    flows = [f for f in flows if not (matches(f) and f.date >= begin)]
            elif kind == "series_amount_change":
                flows = [self._reamount(f, amount, currency, percent) if matches(f) and f.date >= begin else f for f in flows]
            elif kind == "temporary_amount":
                until = _parse_date(e.get("until")) or self.end
                flows = [self._reamount(f, amount, currency, None) if matches(f) and self.start <= f.date <= until else f for f in flows]
            elif kind == "one_time_amount_change":
                upcoming = sorted((i for i, f in enumerate(flows) if matches(f) and f.date >= begin), key=lambda i: flows[i].date)
                if upcoming:
                    flows[upcoming[0]] = self._reamount(flows[upcoming[0]], amount, currency, None)
            elif kind == "occurrence_moved" and on:
                i = self._nearest(flows, cat, direction, on, 31, ("projected", "known"))
                if i is not None:
                    flows[i] = replace(flows[i], date=on, amount=self._convert(flows[i].raw_amount, flows[i].currency, on) if flows[i].currency != self.home else flows[i].amount)
            elif kind in ("series_starts", "confirmed_credit") and direction == "credit" and on and amount is not None:
                if not (self.start <= on <= self.end):
                    continue
                value = self._convert(float(amount), currency, on)
                i = self._nearest(flows, cat, direction, on, self._series_window(cat, direction), ("projected", "known"))
                if i is not None:
                    flows[i] = replace(flows[i], date=on, amount=min(flows[i].amount, value))
                else:
                    flows.append(Flow(date=on, amount=value, raw_amount=float(amount), currency=currency or self.home, direction="credit",
                                      category=cat, description=kind, role=roles.KNOWN_FUTURE, source="evidence"))
        return flows

    def _reamount(self, f: Flow, amount, currency, percent) -> Flow:
        if percent is not None:
            raw = f.raw_amount * (1 + float(percent) / 100.0)
            return replace(f, raw_amount=raw, amount=self._convert(raw, f.currency, f.date))
        if amount is None:
            return f
        return replace(f, raw_amount=float(amount), currency=currency or f.currency, amount=self._convert(float(amount), currency or f.currency, f.date))

    # ---- simulation ------------------------------------------------------------
    def apply_changes(self, changes: Iterable[Change]) -> tuple[list[Flow], float]:
        by_category = {c.category: c for c in changes}
        out, cut = [], 0.0
        for f in self.flows:
            c = by_category.get(f.category)
            if c is None or f.source != "projected" or f.direction != "debit":
                out.append(f)
                continue
            if c.kind == "stop":
                cut += f.amount
                continue
            new_amount = min(f.amount, self._convert(c.new_raw_amount, f.currency, f.date))
            cut += f.amount - new_amount
            out.append(replace(f, amount=new_amount, raw_amount=c.new_raw_amount))
        return out, cut

    def balances(self, payments: Iterable[tuple[date, float]] = (), changes: Iterable[Change] = ()) -> list[float]:
        """Balance after each day's debits (the binding intraday point), for every day in the window."""
        flows, _ = self.apply_changes(changes) if changes else (self.flows, 0.0)
        days = self.switches.window_days + 1
        debits, credits = [0.0] * days, [0.0] * days
        for f in flows:
            i = (f.date - self.start).days
            (credits if f.direction == "credit" else debits)[i] += f.amount
        for d, amount in payments:
            i = (d - self.start).days
            if 0 <= i < days:
                debits[i] += amount
        out, balance = [], self.ledger.profile.balance
        end_of_day = self.switches.intraday == "end_of_day"
        for i in range(days):
            balance -= debits[i]
            if end_of_day:
                balance += credits[i]
                out.append(balance)
            else:
                out.append(balance)
                balance += credits[i]
        return out

    def is_safe(self, payments: Iterable[tuple[date, float]] = (), changes: Iterable[Change] = ()) -> bool:
        return min(self.balances(payments, changes)) >= self.ledger.profile.minimum_balance - EPS

    def safe_amount(self) -> float:
        low = min(self.balances())
        requested = self.ledger.request.requested_amount
        return max(0.0, min(requested, low - self.ledger.profile.minimum_balance))

    def earliest_full_payment(self) -> Optional[date]:
        path = self.balances()
        need = self.ledger.request.requested_amount + self.ledger.profile.minimum_balance
        suffix = float("inf")
        suffix_min = [0.0] * len(path)
        for i in range(len(path) - 1, -1, -1):
            suffix = min(suffix, path[i])
            suffix_min[i] = suffix
        for i, low in enumerate(suffix_min):
            if low >= need - EPS:
                return self.start + timedelta(days=i)
        return None
