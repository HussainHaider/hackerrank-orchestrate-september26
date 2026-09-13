"""Hard contract gate: any violation aborts the run (plan §5.5)."""
from __future__ import annotations

from datetime import date

from .contracts import Dataset

STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
HEADER = ["request_id", "amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan",
          "earliest_date_for_full_payment", "spending_changes_needed", "decision_explanation"]


class ContractError(ValueError):
    pass


def validate_row(row: dict[str, str], ds: Dataset) -> None:
    rid = row["request_id"]
    req = next(r for r in ds.requests if r.request_id == rid)
    profile = ds.profiles[req.user_id]

    def fail(msg: str) -> None:
        raise ContractError(f"{rid}: {msg}")

    safe = float(row["amount_safe_to_pay"])
    if not (0 <= safe <= req.requested_amount + 1e-9):
        fail(f"amount_safe_to_pay {safe} outside [0, requested]")
    status, method = row["affordability_status"], row["recommended_payment_method"]
    if status not in STATUSES or method not in METHODS:
        fail(f"bad enum {status}/{method}")
    earliest = row["earliest_date_for_full_payment"]
    if (status == "affordable_now") != (earliest == req.request_date.isoformat() and method == "full_payment"):
        if status == "affordable_now":
            fail("affordable_now requires full_payment and earliest == request_date")
    payments = [] if row["payment_plan"] == "none" else [(date.fromisoformat(p.split(":")[0]), float(p.split(":")[1])) for p in row["payment_plan"].split("|")]
    if method in ("wait", "not_recommended") and method == "not_recommended" and payments:
        fail("not_recommended must have payment_plan none")
    if method != "not_recommended" and not payments:
        fail("a recommended method needs a payment plan")
    if [d for d, _ in payments] != sorted(d for d, _ in payments):
        fail("payment_plan not chronological")
    if payments and payments[-1][0] > req.deadline:
        fail("plan finishes after the deadline")
    if method == "partial_payment":
        if status != "affordable_with_plan" or len(payments) != 2 or not req.allows_partial_payment:
            fail("partial payment shape")
        if abs(sum(a for _, a in payments) - req.requested_amount) > 0.011 or payments[0] != (req.request_date, safe):
            fail("partial payments must be safe today + remainder")
        if not (0 < safe < req.requested_amount) or payments[1][0].isoformat() != earliest:
            fail("partial second payment must be on the earliest date")
    if method == "installments":
        options = ds.options_by_request.get(rid, [])
        if not any(o.method == "installments" and len(payments) == o.number_of_payments
                   and all(abs(a - o.payment_amount) < 0.005 for _, a in payments) and payments[0][0] == o.first_payment_date
                   for o in options):
            fail("installment plan does not match a supplied option")
    if method in ("full_payment", "partial_payment", "installments", "wait") and method.replace("_payment", "") not in {m.replace("_payment", "") for m in profile.methods} and method != "wait":
        fail(f"user does not accept {method}")
    if method == "wait" and "full_payment" not in profile.methods:
        fail("wait requires full_payment acceptance")
    changes = [] if row["spending_changes_needed"] == "none" else row["spending_changes_needed"].split("|")
    if len(changes) > 3:
        fail("more than three spending changes")
    seen = set()
    for c in changes:
        parts = c.split(":")
        event = ds.events_by_id.get(parts[1])
        if event is None or event.user_id != req.user_id:
            fail(f"change targets unknown event {parts[1]}")
        if event.category in profile.protected:
            fail(f"change touches protected category {event.category}")
        if parts[0] == "stop" and not (event.flexibility in ("stoppable", "reducible_or_stoppable") and event.category in profile.stoppable_categories):
            fail(f"stop not permitted on {parts[1]}")
        if parts[0] == "reduce_to" and not (event.flexibility in ("reducible", "reducible_or_stoppable") and event.category in profile.reducible_categories):
            fail(f"reduce not permitted on {parts[1]}")
        if parts[1] in seen:
            fail("stop and reduce on the same event")
        seen.add(parts[1])
    if not row["decision_explanation"].strip():
        fail("empty explanation")


def validate_rows(rows: list[dict[str, str]], ds: Dataset) -> None:
    ids = [r["request_id"] for r in rows]
    expected = [r.request_id for r in ds.requests]
    if sorted(ids) != sorted(expected) or len(set(ids)) != len(ids):
        raise ContractError("output must have exactly one row per request")
    for row in rows:
        validate_row(row, ds)
