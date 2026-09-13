"""Per-request engine: forecast -> decide -> explain -> row; validate all rows; write CSV."""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from .config import Switches
from .context import EngineContext
from .explain import explain
from .formatting import plan_amount, raw_amount
from .planner import decide
from .validate import HEADER, validate_rows

log = logging.getLogger(__name__)


def build_rows(ctx: EngineContext) -> list[dict[str, str]]:
    rows = []
    for req in ctx.ds.requests:
        fc = ctx.forecast(req)
        decision = decide(fc, ctx.ds.options_by_request.get(req.request_id, []), ctx.switches.change_order)
        plan = decision.plan
        descriptions = {e.event_id: e.description for e in ctx.ds.events_by_user.get(req.user_id, [])}
        changes = "none"
        if plan and plan.changes:
            parts = []
            for c in sorted(plan.changes, key=lambda c: int(c.target_event_id.split("_")[1])):
                parts.append(f"stop:{c.target_event_id}" if c.kind == "stop" else f"reduce_to:{c.target_event_id}:{plan_amount(c.new_raw_amount)}")
            changes = "|".join(parts)
        rows.append({
            "request_id": req.request_id,
            "amount_safe_to_pay": raw_amount(decision.safe_amount),
            "affordability_status": decision.status,
            "recommended_payment_method": decision.method,
            "payment_plan": "|".join(f"{d.isoformat()}:{plan_amount(a)}" for d, a in plan.payments) if plan else "none",
            "earliest_date_for_full_payment": decision.earliest.isoformat() if decision.earliest else "",
            "spending_changes_needed": changes,
            "decision_explanation": explain(decision, req, fc.ledger.profile, descriptions),
        })
    return rows


def write_rows(rows: list[dict[str, str]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def run_engine(dataset_dir: Path, requests_file: Optional[Path], out: Path, switches: Switches = Switches()) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ctx = EngineContext.load(dataset_dir, requests_file, switches)
    rows = build_rows(ctx)
    validate_rows(rows, ctx.ds)
    write_rows(rows, out)
    print(f"wrote {len(rows)} rows to {out}")
    return 0
