"""Buy or Wait? entry point.

    python3 code/main.py                       # 250 requests -> dataset/output.csv (offline, committed evidence)
    python3 code/main.py --requests dataset/sample_requests.csv --out .scratch/sample_output.csv
    python3 code/main.py --extract             # the single uncached LLM extraction run (needs OPENAI_API_KEY)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buyorwait.config import DATASET_DIR, EVIDENCE_DATA_DIR  # noqa: E402
from buyorwait.loaders import load_dataset, load_requests  # noqa: E402


def _extract(dataset_dir: Path) -> int:
    from buyorwait.evidence import extract

    ds = load_dataset(dataset_dir)
    ds.requests = ds.requests + load_requests(dataset_dir / "sample_requests.csv")  # every user's request date
    summary = extract.run(ds, EVIDENCE_DATA_DIR)
    print(summary)
    return 1 if summary["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=DATASET_DIR)
    parser.add_argument("--requests", type=Path, default=None, help="requests CSV (default: <dataset>/requests.csv)")
    parser.add_argument("--out", type=Path, default=None, help="output CSV (default: <dataset>/output.csv)")
    parser.add_argument("--extract", action="store_true", help="run the uncached LLM extraction and rewrite evidence/data")
    args = parser.parse_args(argv)
    if args.extract:
        return _extract(args.dataset)
    from buyorwait.pipeline import run_engine

    return run_engine(args.dataset, args.requests, args.out or args.dataset / "output.csv")


if __name__ == "__main__":
    raise SystemExit(main())
