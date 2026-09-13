"""Critical-path tests: ledger rules, projection, evidence safety, planner ranking/status, formatting, validator."""
from dataclasses import replace
from datetime import date

import pytest

from buyorwait.config import DATASET_DIR, EVIDENCE_DATA_DIR, Switches
from buyorwait.context import EngineContext
from buyorwait.evidence.apply import load_effects
from buyorwait.forecast import Change
from buyorwait.formatting import long_date, money, plan_amount, raw_amount
from buyorwait.planner import Plan, best_change_set, decide, _change_candidates
from buyorwait.pipeline import build_rows
from buyorwait.recurrence import MONTHLY, Series, occurrence_dates
from buyorwait.validate import ContractError, validate_row


@pytest.fixture(scope="module")
def eval_ctx():
    return EngineContext.load(DATASET_DIR)


@pytest.fixture(scope="module")
def sample_ctx():
    return EngineContext.load(DATASET_DIR, DATASET_DIR / "sample_requests.csv")


def _request(ctx, rid):
    return next(r for r in ctx.ds.requests if r.request_id == rid)


# ---- ledger ---------------------------------------------------------------------------------
def test_disputed_duplicate_charge_is_reserved(eval_ctx):
    fc = eval_ctx.forecast(next(r for r in eval_ctx.ds.requests if r.user_id == "user_138"))
    assert "event_12709" in {p.event_id for p in fc.ledger.pending}
    assert any(f.event_id == "event_12709" and f.date == fc.start for f in fc.flows)


def test_failed_debit_counted_once_through_linked_retry(eval_ctx):
    fc = eval_ctx.forecast(next(r for r in eval_ctx.ds.requests if r.user_id == "user_91"))
    ids = [f.event_id for f in fc.flows]
    assert "event_8575" not in ids          # the failed attempt
    assert ids.count("event_8576") == 1     # its scheduled retry


def test_internal_transfer_message_changes_nothing(sample_ctx):
    req = _request(sample_ctx, "request_18")
    with_evidence = sample_ctx.forecast(req).safe_amount()
    effects = sample_ctx.effects
    try:
        sample_ctx.effects = {k: v for k, v in effects.items() if k != "user_18"}
        without = sample_ctx.forecast(req).safe_amount()
    finally:
        sample_ctx.effects = effects
    assert with_evidence == without


def test_foreign_salary_is_converted(sample_ctx):
    fc = sample_ctx.forecast(_request(sample_ctx, "request_25"))
    salary = [f for f in fc.flows if f.direction == "credit"]
    assert salary and all(f.amount > 1_000_000 for f in salary)  # USD 1,800 in IDR


# ---- projection -----------------------------------------------------------------------------
def test_monthly_projection_stays_on_day_of_month():
    s = Series(("salary", "credit"), "salary", "credit", MONTHLY, 15, date(2025, 12, 15), 1000.0, "EUR", "fixed", None, 5)
    assert occurrence_dates(s, date(2026, 1, 1), date(2026, 3, 31)) == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    end_of_month = replace(s, day_of_month=31)
    assert occurrence_dates(end_of_month, date(2026, 1, 1), date(2026, 3, 31)) == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_step_projection_from_last_occurrence():
    s = Series(("groceries", "debit"), "groceries", "debit", 7, None, date(2026, 1, 1), 50.0, "EUR", "fixed", None, 20)
    assert occurrence_dates(s, date(2026, 1, 5), date(2026, 1, 20)) == [date(2026, 1, 8), date(2026, 1, 15)]


# ---- evidence safety ------------------------------------------------------------------------
def test_solicitation_and_no_action_effects_never_reach_engine(eval_ctx):
    effects = load_effects(EVIDENCE_DATA_DIR / "evidence.json", eval_ctx.ds)
    assert not any(e["message_id"] == "message_67" for e in effects.get("user_88", []))
    assert all(e["type"] not in ("solicitation", "internal_transfer", "disputed_charge") for es in effects.values() for e in es)


# ---- planner --------------------------------------------------------------------------------
def test_spec_ranking_order():
    d = date(2026, 1, 1)
    full = Plan("full_payment", [(d, 100.0)])
    installments = Plan("installments", [(d, 40.0), (date(2026, 2, 1), 40.0), (date(2026, 3, 1), 40.0)])
    wait = Plan("wait", [(date(2026, 1, 15), 100.0)])
    assert min([installments, wait, full], key=Plan.rank_key) is full       # same total, earlier start
    cheaper_later = Plan("installments", [(date(2026, 1, 5), 49.0), (date(2026, 2, 5), 49.0)])
    assert min([full, cheaper_later], key=Plan.rank_key) is cheaper_later   # total paid beats start date


@pytest.mark.parametrize("rid,status,method", [
    ("request_09", "affordable_now", "full_payment"),
    ("request_17", "affordable_with_plan", "installments"),
    ("request_03", "affordable_later", "wait"),
    ("request_19", "affordable_with_plan", "partial_payment"),
    ("request_05", "not_affordable", "not_recommended"),
])
def test_status_table_on_samples(sample_ctx, rid, status, method):
    req = _request(sample_ctx, rid)
    decision = decide(sample_ctx.forecast(req), sample_ctx.ds.options_by_request[rid])
    assert (decision.status, decision.method) == (status, method)


def test_change_set_is_safe_and_minimal_cut(sample_ctx):
    base = _request(sample_ctx, "request_21")
    headroom = sample_ctx.forecast(replace(base, requested_amount=10**9)).safe_amount()
    req = replace(base, requested_amount=round(headroom + 20.0, 2))  # a 20.00 gap that needs spending changes
    fc = sample_ctx.forecast(req)
    payments = [(req.request_date, req.requested_amount)]
    assert not fc.is_safe(payments)
    best = best_change_set(fc, payments, "min_cut")
    assert best is not None
    combo, cut = best
    assert fc.is_safe(payments, combo)
    for c in _change_candidates(fc):  # no single passing change is cheaper
        if fc.is_safe(payments, (c,)):
            assert fc.apply_changes((c,))[1] >= cut - 1e-9


def test_protected_categories_never_changed(eval_ctx):
    for row in build_rows(eval_ctx):
        if row["spending_changes_needed"] == "none":
            continue
        req = _request(eval_ctx, row["request_id"])
        profile = eval_ctx.ds.profiles[req.user_id]
        for change in row["spending_changes_needed"].split("|"):
            assert eval_ctx.ds.events_by_id[change.split(":")[1]].category not in profile.protected


# ---- formatting & validator -----------------------------------------------------------------
def test_formats_match_samples():
    assert raw_amount(603.3) == "603.3" and raw_amount(17229139.2) == "17229139.2" and raw_amount(25256.0) == "25256"
    assert plan_amount(620.4) == "620.40" and plan_amount(23.5) == "23.50" and plan_amount(665950.0) == "665950"
    assert money("IDR", 15952906.67) == "IDR 15,952,906.67" and money("ZAR", 25256) == "ZAR 25,256"
    assert long_date(date(2025, 8, 8)) == "8 August 2025"


def test_validator_rejects_bad_rows(sample_ctx):
    good = {r["request_id"]: r for r in build_rows(sample_ctx)}["request_09"]
    validate_row(good, sample_ctx.ds)
    with pytest.raises(ContractError):
        validate_row({**good, "amount_safe_to_pay": "999999"}, sample_ctx.ds)
    with pytest.raises(ContractError):
        validate_row({**good, "payment_plan": "2026-07-04:10|2026-07-01:156.61"}, sample_ctx.ds)
    with pytest.raises(ContractError):
        validate_row({**good, "affordability_status": "maybe"}, sample_ctx.ds)


def test_full_run_is_deterministic(eval_ctx):
    assert build_rows(eval_ctx) == build_rows(eval_ctx)
