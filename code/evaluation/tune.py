"""Grid over calibration switches, scored on every column against the 25 samples (plan §6)."""
from __future__ import annotations

import itertools
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from buyorwait.config import DATASET_DIR, Switches  # noqa: E402
from buyorwait.context import EngineContext  # noqa: E402
from buyorwait.pipeline import build_rows  # noqa: E402
from score import _rows, score  # noqa: E402

GRID = {
    "expense_estimator": ["last", "mean", "median", "p75"],
    "recent_occurrences": [3, 6, 12, 1000],
    "variable_income": ["none", "low_percentile"],
    "pending_in_balance": [False, True],
}


def headline(r: dict) -> float:
    cols = ["status_acc", "method_acc", "plan_exact", "earliest_exact", "changes_exact", "safe_within_1pct"]
    return sum(r[c] for c in cols) / len(cols)


def main() -> None:
    gold = _rows(DATASET_DIR / "sample_requests.csv")
    ctx = EngineContext.load(DATASET_DIR, DATASET_DIR / "sample_requests.csv")
    results = []
    keys = list(GRID)
    for values in itertools.product(*GRID.values()):
        ctx.switches = replace(Switches(), **dict(zip(keys, values)))
        preds = {r["request_id"]: r for r in build_rows(ctx)}
        r = score(preds, gold)
        results.append((headline(r), r, dict(zip(keys, values))))
    results.sort(key=lambda x: -x[0])
    for h, r, cfg in results[:12]:
        print(f"{h:.3f} status={r['status_acc']:.2f} method={r['method_acc']:.2f} plan={r['plan_exact']:.2f} earliest={r['earliest_exact']:.2f} "
              f"changes={r['changes_exact']:.2f} safe1%={r['safe_within_1pct']:.2f} safeX={r['safe_exact']:.2f} mape={r['safe_median_ape']:.3f} | {cfg}")


if __name__ == "__main__":
    main()
