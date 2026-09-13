"""Everything the per-request engine needs, loaded once."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import EVIDENCE_DATA_DIR, Switches
from .contracts import Dataset, Request
from .evidence.apply import load_effects, load_image_amounts
from .forecast import Forecast
from .ledger import build_ledger
from .loaders import load_dataset
from .vocabulary import load_vocabulary


@dataclass
class EngineContext:
    ds: Dataset
    vocab: dict[str, str]
    image_amounts: dict[str, dict]
    effects: dict[str, list[dict]]
    switches: Switches

    @classmethod
    def load(cls, dataset_dir: Path, requests_file: Optional[Path] = None, switches: Switches = Switches(),
             evidence_dir: Path = EVIDENCE_DATA_DIR) -> "EngineContext":
        ds = load_dataset(dataset_dir, requests_file)
        return cls(ds=ds, vocab=load_vocabulary(evidence_dir / "vocabulary.json"),
                   image_amounts=load_image_amounts(evidence_dir / "image_amounts.json"),
                   effects=load_effects(evidence_dir / "evidence.json", ds), switches=switches)

    def forecast(self, request: Request) -> Forecast:
        ledger = build_ledger(self.ds, request, self.vocab, self.image_amounts)
        return Forecast(ledger, self.ds.fx, self.switches, self.effects.get(request.user_id, []))
