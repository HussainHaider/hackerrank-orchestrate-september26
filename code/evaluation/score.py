"""Score a prediction CSV against the labelled samples, column by column (plan §6).

    python3 code/evaluation/score.py --pred .scratch/sample_output.csv [--verbose]
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["request_id"]: r for r in csv.DictReader(fh)}


def _plan(text: str) -> list[tuple[str, float]]:
    return [] if text in ("", "none") else [(p.split(":")[0], round(float(p.split(":")[1]), 2)) for p in text.split("|")]


def _changes(text: str) -> set[str]:
    return set() if text in ("", "none") else {re.sub(r":(\d+(?:\.\d+)?)$", lambda m: f":{float(m.group(1)):.2f}", c) for c in text.split("|")}


def _template(text: str) -> str:
    return re.sub(r"[A-Z]{3} [\d,]+(?:\.\d+)?|\d{1,2} [A-Z][a-z]+ \d{4}|\d+ installments|the [a-z ]+? (?=to|,|and)", "#", text)


def score(pred: dict[str, dict[str, str]], gold: dict[str, dict[str, str]], verbose: bool = False) -> dict[str, float]:
    ids = sorted(gold)
    n = len(ids)
    safe_exact = safe_1pct = status = method = plan = earliest = changes = template = 0
    ape, days_off = [], []
    confusion = Counter()
    for rid in ids:
        g, p = gold[rid], pred.get(rid)
        if p is None:
            continue
        gs, ps = float(g["amount_safe_to_pay"]), float(p["amount_safe_to_pay"])
        safe_exact += abs(gs - ps) < 0.005
        safe_1pct += abs(gs - ps) <= 0.01 * max(1.0, gs)
        ape.append(abs(gs - ps) / max(1.0, gs))
        status += g["affordability_status"] == p["affordability_status"]
        confusion[(g["affordability_status"], p["affordability_status"])] += 1
        method += g["recommended_payment_method"] == p["recommended_payment_method"]
        plan += _plan(g["payment_plan"]) == _plan(p["payment_plan"])
        earliest += g["earliest_date_for_full_payment"] == p["earliest_date_for_full_payment"]
        if g["earliest_date_for_full_payment"] and p["earliest_date_for_full_payment"]:
            days_off.append(abs((date.fromisoformat(g["earliest_date_for_full_payment"]) - date.fromisoformat(p["earliest_date_for_full_payment"])).days))
        changes += _changes(g["spending_changes_needed"]) == _changes(p["spending_changes_needed"])
        template += _template(g["decision_explanation"]) == _template(p["decision_explanation"])
        if verbose:
            flags = "".join(k for k, ok in [("S", abs(gs - ps) < 0.005), ("t", g["affordability_status"] == p["affordability_status"]),
                                             ("m", g["recommended_payment_method"] == p["recommended_payment_method"]),
                                             ("p", _plan(g["payment_plan"]) == _plan(p["payment_plan"])),
                                             ("e", g["earliest_date_for_full_payment"] == p["earliest_date_for_full_payment"]),
                                             ("c", _changes(g["spending_changes_needed"]) == _changes(p["spending_changes_needed"]))] if ok)
            print(f"{rid:<11} [{flags:<6}] safe {ps:>14,.2f}/{gs:>14,.2f} | {p['affordability_status']:<20}/{g['affordability_status']:<20} "
                  f"| {p['recommended_payment_method']:<15}/{g['recommended_payment_method']:<15} | {p['earliest_date_for_full_payment'] or '-':<10}/{g['earliest_date_for_full_payment'] or '-':<10} | {p['spending_changes_needed']} / {g['spending_changes_needed']}")
    result = {
        "rows": n, "safe_exact": safe_exact / n, "safe_within_1pct": safe_1pct / n, "safe_median_ape": statistics.median(ape) if ape else 1.0,
        "status_acc": status / n, "method_acc": method / n, "plan_exact": plan / n, "earliest_exact": earliest / n,
        "earliest_mean_days_off": statistics.mean(days_off) if days_off else 0.0, "changes_exact": changes / n, "explanation_template": template / n,
    }
    if verbose:
        print("\nstatus confusion (gold -> pred):", dict(confusion))
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--gold", type=Path, default=REPO / "dataset" / "sample_requests.csv")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    result = score(_rows(args.pred), _rows(args.gold), args.verbose)
    for k, v in result.items():
        print(f"{k:<26}{v:.3f}" if isinstance(v, float) else f"{k:<26}{v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
