"""Grid over the capacity switches, scored on the 25 samples (safe amount + earliest date)."""
import csv
import itertools
import statistics
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from buyorwait.config import DATASET_DIR, Switches  # noqa: E402
from buyorwait.context import EngineContext  # noqa: E402

labels = {r["request_id"]: r for r in csv.DictReader((DATASET_DIR / "sample_requests.csv").open(encoding="utf-8"))}
ctx = EngineContext.load(DATASET_DIR, DATASET_DIR / "sample_requests.csv")
grid = itertools.product(["last", "mean", "median", "p75", "max"], ["end_of_day"], [89, 90],
                         [False, True], ["none", "low_percentile"], [0.25, 0.5], [0, 1])
results = []
for est, intraday, window, pend, var, inc, offset in grid:
    ctx.switches = replace(Switches(), expense_estimator=est, intraday=intraday, window_days=window, pending_in_balance=pend,
                           variable_income=var, income_percentile=inc, projection_offset=offset)
    exact = within = dates = 0
    errs = []
    for req in ctx.ds.requests:
        fc = ctx.forecast(req)
        safe = round(fc.safe_amount(), 2)
        true = float(labels[req.request_id]["amount_safe_to_pay"])
        e = fc.earliest_full_payment()
        exact += abs(safe - true) < 0.015
        within += abs(safe - true) <= 0.01 * max(1, true)
        dates += (e.isoformat() if e else "") == labels[req.request_id]["earliest_date_for_full_payment"]
        errs.append(abs(safe - true) / max(1.0, true))
    results.append((exact, dates, within, statistics.median(errs), est, intraday, window, pend, var, inc, offset))
results.sort(key=lambda r: (-(r[0] + r[1]), -r[2], r[3]))
print("exact dates within1% medianAPE | estimator intraday window pending_in_balance variable_income income_pct offset")
for r in results[:15]:
    print(f"{r[0]:>5} {r[1]:>5} {r[2]:>8} {r[3]:>10.3f} | {r[4]:<7}{r[5]:<13}{r[6]:<4}{str(r[7]):<6}{r[8]:<15}{r[9]:<5}{r[10]}")
