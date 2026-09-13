import sys
from pathlib import Path

import pytest

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from buyorwait.config import DATASET_DIR  # noqa: E402
from buyorwait.loaders import load_dataset  # noqa: E402


@pytest.fixture(scope="session")
def dataset():
    return load_dataset(DATASET_DIR)


@pytest.fixture(scope="session")
def sample_dataset():
    return load_dataset(DATASET_DIR, DATASET_DIR / "sample_requests.csv")
