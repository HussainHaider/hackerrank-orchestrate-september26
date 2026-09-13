"""Score the capacity outputs (safe amount, earliest date) against the 25 samples, before the planner exists."""
import csv
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from buyorwait.config import DATASET_DIR, Switches  # noqa: E402
from buyorwait.context import EngineContext  # noqa: E402

labels = {r["request_id"]: r for r in csv.DictReader((DATASET_DIR / "sample_requests.csv").open(encoding="utf-8"))}


def score(switches: Switches, verbose: bool = False, no_evidence: bool = False):
    ctx = EngineContext.load(DATASET_DIR, DATASET_DIR / "sample_requests.csv", switches)
    if no_evidence:
        ctx.effects = {}
    exact = within1 = date_exact = 0
    rows = []
    for req in ctx.ds.requests:
        fc = ctx.forecast(req)
        safe = round(fc.safe_amount(), 2)
        earliest = fc.earliest_full_payment()
        lab = labels[req.request_id]
        true_safe = float(lab["amount_safe_to_pay"])
        true_date = lab["earliest_date_for_full_payment"] or None
        pred_date = earliest.isoformat() if earliest else None
        ok = abs(safe - true_safe) < 0.015
        exact += ok
        within1 += abs(safe - true_safe) <= 0.01 * max(1.0, true_safe)
        date_exact += pred_date == true_date
        rows.append((req.request_id, safe, true_safe, pred_date, true_date, ok))
    if verbose:
        for rid, s, t, pd, td, ok in rows:
            print(f"  {rid:<11} safe {s:>15,.2f} vs {t:>15,.2f} {'OK ' if ok else 'x  '} ratio={s/t if t else 0:>6.2f} | earliest {pd} vs {td} {'OK' if pd == td else 'x'}")
    return exact, within1, date_exact


if __name__ == "__main__":
    base = Switches()
    print("default switches:", base)
    print("with evidence    -> safe exact/within1%/date exact:", score(base, verbose=True))
    print("without evidence -> ", score(base, no_evidence=True))
