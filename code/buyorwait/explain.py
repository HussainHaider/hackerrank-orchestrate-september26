"""Templated decision_explanation (shapes taken from the 25 labelled samples, plus two unlabelled cases)."""
from __future__ import annotations

from .contracts import Profile, Request
from .formatting import long_date, money
from .planner import FULL, INSTALLMENTS, NONE, PARTIAL, WAIT, Decision


def _changes_clause(decision: Decision, currency: str, descriptions: dict[str, str]) -> str:
    parts = []
    for c in decision.plan.changes:
        name = descriptions.get(c.target_event_id, c.category).lower()
        parts.append(f"stop the {name}" if c.kind == "stop" else f"reduce the {name} to {money(currency, c.new_raw_amount)}")
    text = " and ".join(parts)
    return text[0].upper() + text[1:]


def explain(decision: Decision, request: Request, profile: Profile, descriptions: dict[str, str]) -> str:
    cur = profile.home_currency
    minimum = money(cur, profile.minimum_balance)
    amount = money(cur, request.requested_amount)
    plan = decision.plan

    if decision.method == NONE:
        if decision.earliest:
            reason = ("that is after " + long_date(request.deadline)) if decision.earliest > request.deadline else "full payment is not a method you accept"
            return f"Do not pay now. The full {amount} becomes safe on {long_date(decision.earliest)}, but {reason}."
        if profile.methods == {PARTIAL} and request.allows_partial_payment:
            return (f"Do not proceed with the {amount} request. Although {money(cur, decision.safe_amount)} is available today, "
                    "the full amount cannot be completed safely within 90 days.")
        return f"Do not make this payment by {long_date(request.deadline)}. None of the available options keeps the {minimum} minimum protected."

    prefix = (_changes_clause(decision, cur, descriptions) + ", then ") if plan.changes else ""
    if decision.method == FULL:
        if plan.changes:
            return f"{prefix}pay {amount} today. This leaves at least {minimum} available."
        return f"Pay {amount} today. This leaves at least {minimum} available over the next 90 days."
    if decision.method == WAIT:
        day = long_date(plan.payments[0][0])
        if plan.payments[0][0] < request.deadline:
            return f"Wait until {day}, then pay {amount} in full. Paying sooner would put the {minimum} minimum at risk."
        return f"Pay {amount} in full on {day}. Paying earlier would take the balance below the {minimum} minimum."
    if decision.method == PARTIAL:
        (d0, a0), (d1, a1) = plan.payments
        return (f"Pay {money(cur, a0)} today and the remaining {money(cur, a1)} on {long_date(d1)}. "
                f"This completes the full request and keeps the {minimum} minimum protected.")
    if decision.method == INSTALLMENTS:
        n, each, start = len(plan.payments), plan.payments[0][1], plan.payments[0][0]
        lead = f"{prefix}use" if plan.changes else "Use"
        return f"{lead} {n} installments of {money(cur, each)}, starting {long_date(start)}. This leaves at least {minimum} available."
    raise ValueError(decision.method)
