"""Paths, horizon, and the calibration switches (plan §6)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_dataset() -> Path:
    """BUYORWAIT_DATASET, else the nearest dataset/ beside or above the code (works in the repo and from code.zip)."""
    if os.environ.get("BUYORWAIT_DATASET"):
        return Path(os.environ["BUYORWAIT_DATASET"]).resolve()
    for base in (Path(__file__).resolve().parents[1], REPO_ROOT, Path.cwd()):
        if (base / "dataset" / "requests.csv").exists():
            return base / "dataset"
    return REPO_ROOT / "dataset"


DATASET_DIR = _find_dataset()
EVIDENCE_DATA_DIR = Path(__file__).resolve().parent / "evidence" / "data"

FORECAST_DAYS = 90
MAX_SPENDING_CHANGES = 3


@dataclass(frozen=True)
class Switches:
    """The only tuned knobs. Each one is a reading of the spec, not a fitted constant."""

    pending_in_balance: bool = False      # True: current_available_balance already nets pending debits
    change_order: str = "min_cut"         # "min_cut" | "fewest"
    recent_occurrences: int = 6           # how many recent occurrences feed amount estimates
    expense_estimator: str = "mean"        # last | mean | median | p75 | p90 | max, over recent occurrences
    intraday: str = "end_of_day"        # debits_first | end_of_day: when a day's balance is checked
    window_days: int = FORECAST_DAYS      # last forecast day = request date + window_days
    projection_offset: int = 0            # first day a projected occurrence may fall on (0 = request date)
    income_percentile: float = 0.25       # low estimate for regular income streams
    variable_income: str = "low_percentile"  # "none" | "low_percentile"
