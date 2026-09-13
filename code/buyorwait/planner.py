"""Safe-plan enumeration, spending changes, ranking and status (plan §5.1–§5.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from typing import Optional

from .config import MAX_SPENDING_CHANGES
from .contracts import PaymentOption
from .forecast import Change, Forecast
from .formatting import floor_cents

FULL, PARTIAL, INSTALLMENTS, WAIT, NONE = "full_payment", "partial_payment", "installments", "wait", "not_recommended"


@dataclass
class Plan:
    method: str
    payments: list[tuple[date, float]]
    option: Optional[PaymentOption] = None
    changes: tuple[Change, ...] = ()
    cut: float = 0.0

    @property
    def total(self) -> float:
        return round(sum(a for _, a in self.payments), 2)

    def rank_key(self) -> tuple:
        # spec rules 3-6: total paid, earlier start, fewer payments, lowest payment_option_id
        return (self.total, self.payments[0][0], len(self.payments), self.option.ordinal if self.option else 0)


@dataclass
class Decision:
    safe_amount: float
    earliest: Optional[date]
    plan: Optional[Plan]
    status: str
    method: str
    notes: dict = field(default_factory=dict)


def installment_schedule(option: PaymentOption) -> list[tuple[date, float]]:
    step = timedelta(days=option.frequency_days or 0)
    return [(option.first_payment_date + step * k, option.payment_amount) for k in range(option.number_of_payments)]


def _change_candidates(fc: Forecast) -> list[Change]:
    ledger, profile = fc.ledger, fc.ledger.profile
    projected = {s.category for s in fc.series if s.direction == "debit"}
    out: list[Change] = []
    for category in sorted(projected):
        target = ledger.latest_debit_by_category.get(category)
        if target is None or category in profile.protected:
            continue
        if target.flexibility in ("stoppable", "reducible_or_stoppable") and category in profile.stoppable_categories:
            out.append(Change("stop", category, target.event_id))
        if (target.flexibility in ("reducible", "reducible_or_stoppable") and category in profile.reducible_categories
                and target.minimum_allowed_amount is not None):
            out.append(Change("reduce", category, target.event_id, target.minimum_allowed_amount))
    return out


def best_change_set(fc: Forecast, payments: list[tuple[date, float]], order: str) -> Optional[tuple[tuple[Change, ...], float]]:
    candidates = _change_candidates(fc)
    found = []
    for size in range(1, MAX_SPENDING_CHANGES + 1):
        for combo in combinations(candidates, size):
            if len({c.category for c in combo}) < size:
                continue  # stop and reduce on the same series are mutually exclusive
            if fc.is_safe(payments, combo):
                _, cut = fc.apply_changes(combo)
                ids = tuple(sorted(int(c.target_event_id.split("_")[1]) for c in combo))
                found.append(((round(cut, 6), size, ids) if order == "min_cut" else (size, round(cut, 6), ids), combo, cut))
    if not found:
        return None
    _, combo, cut = min(found, key=lambda x: x[0])
    return combo, cut


def decide(fc: Forecast, options: list[PaymentOption], change_order: str = "min_cut") -> Decision:
    req, profile = fc.ledger.request, fc.ledger.profile
    rd, amount, deadline = req.request_date, req.requested_amount, req.deadline
    methods = profile.methods
    safe = floor_cents(fc.safe_amount())
    earliest = fc.earliest_full_payment()

    installment_options = []
    if INSTALLMENTS in methods and profile.max_installment_months is not None:
        for o in sorted(options, key=lambda o: o.ordinal):
            if o.method == INSTALLMENTS and o.number_of_payments <= profile.max_installment_months:
                schedule = installment_schedule(o)
                if schedule[0][0] >= rd and schedule[-1][0] <= deadline:
                    installment_options.append((o, schedule))
    full_option = next((o for o in options if o.method == FULL), None)

    # Stage A: no spending changes
    stage_a: list[Plan] = []
    if FULL in methods and fc.is_safe([(rd, amount)]):
        stage_a.append(Plan(FULL, [(rd, amount)], full_option))
    if FULL in methods and earliest and rd < earliest <= deadline:
        stage_a.append(Plan(WAIT, [(earliest, amount)], full_option))
    if (PARTIAL in methods and req.allows_partial_payment and 0 < safe < amount and earliest and earliest <= deadline
            and fc.is_safe([(rd, safe), (earliest, round(amount - safe, 2))])):
        stage_a.append(Plan(PARTIAL, [(rd, safe), (earliest, round(amount - safe, 2))]))
    for o, schedule in installment_options:
        if fc.is_safe(schedule):
            stage_a.append(Plan(INSTALLMENTS, schedule, o))

    winner: Optional[Plan] = min(stage_a, key=Plan.rank_key) if stage_a else None

    # Stage B: only when nothing works without changes; every schedule ties on rule 2, then spec order
    if winner is None:
        stage_b: list[Plan] = []
        schedules = ([(FULL, [(rd, amount)], full_option)] if FULL in methods else []) + [(INSTALLMENTS, s, o) for o, s in installment_options]
        for method, schedule, option in schedules:
            best = best_change_set(fc, schedule, change_order)
            if best:
                stage_b.append(Plan(method, schedule, option, best[0], best[1]))
        winner = min(stage_b, key=Plan.rank_key) if stage_b else None

    if winner is None:
        status = "affordable_later" if earliest else "not_affordable"
        return Decision(safe, earliest, None, status, NONE)
    if winner.method == FULL and not winner.changes:
        status = "affordable_now"
    elif winner.method == WAIT:
        status = "affordable_later"
    else:
        status = "affordable_with_plan"
    return Decision(safe, earliest, winner, status, winner.method)
