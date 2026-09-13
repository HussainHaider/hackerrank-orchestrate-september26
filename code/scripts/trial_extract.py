"""Trial the message/image extractors on a handful of hard cases; writes to .scratch only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from buyorwait.config import DATASET_DIR, REPO_ROOT  # noqa: E402
from buyorwait.evidence import extract  # noqa: E402
from buyorwait.loaders import load_dataset  # noqa: E402

ids = sys.argv[1].split(",")
ds = load_dataset(DATASET_DIR, DATASET_DIR / "sample_requests.csv")
full = load_dataset(DATASET_DIR)
ds.requests = ds.requests + full.requests  # message context needs every user's request date
msgs = [m for ms in ds.messages_by_user.values() for m in ms if m.message_id in ids]
out = REPO_ROOT / ".scratch" / "trial_extract"
summary = extract.run(ds, out, messages=msgs, image_events=[], include_vocabulary=False, workers=7)
print(summary)
for mid, value in json.loads((out / "evidence.json").read_text())["messages"].items():
    print(f"\n{mid} ({value['user_id']}, linked={value['related_event_id']})")
    for eff in value["effects"]:
        print("  ", {k: v for k, v in eff.items() if v not in (None, "")})
