"""Print series, flows and the low point for one or more requests."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from buyorwait.config import DATASET_DIR  # noqa: E402
from buyorwait.context import EngineContext  # noqa: E402

requests_file = DATASET_DIR / ("sample_requests.csv" if sys.argv[1].split(",")[0] <= "request_25" else "requests.csv")
ctx = EngineContext.load(DATASET_DIR, requests_file)
for rid in sys.argv[1].split(","):
    req = next(r for r in ctx.ds.requests if r.request_id == rid)
    fc = ctx.forecast(req)
    p = fc.ledger.profile
    print(f"\n===== {rid} {req.user_id} rd={req.request_date} bal={p.balance} min={p.minimum_balance} req={req.requested_amount} {p.home_currency}")
    for s in sorted(fc.series, key=lambda s: (s.direction, s.category)):
        print(f"  series {s.key} cadence={s.cadence} dom={s.day_of_month} last={s.last_date} amt={s.raw_amount:g} {s.currency} n={s.occurrences} flex={s.flexibility}")
    for k in fc.ledger.known: print(f"  known  {k.date} {k.direction} {k.category} {k.description} {k.amount:g} role={k.role}")
    for k in fc.ledger.pending: print(f"  pending {k.date} {k.category} {k.description} {k.amount:g}")
    for e in ctx.effects.get(req.user_id, []): print(f"  effect {e['type']} {e['category']}/{e['direction']} amt={e['amount']} pct={e['percent']} date={e['date']} until={e['until']}")
    bal = fc.balances()
    low_i = min(range(len(bal)), key=bal.__getitem__)
    monthly = defaultdict(float)
    for f in fc.flows:
        monthly[(f.date.strftime('%Y-%m'), f.direction)] += f.amount
    print("  month totals:", {k: round(v, 2) for k, v in sorted(monthly.items())})
    print(f"  low point day {low_i} ({fc.start.toordinal()+low_i and __import__('datetime').date.fromordinal(fc.start.toordinal()+low_i)}) balance={bal[low_i]:.2f} safe={fc.safe_amount():.2f}")
    last_hist = max(f.date for f in fc.ledger.history)
    print(f"  history ends {last_hist}; categories in history: {sorted({(f.category, f.direction, f.role) for f in fc.ledger.history if f.direction=='credit'})}")
