"""Load committed evidence and keep only effects whose targets exist in the user's own ledger (plan §3.3)."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from ..contracts import Dataset

log = logging.getLogger(__name__)

NO_ENGINE_ACTION = {
    "already_settled", "failed_debit_retry", "internal_transfer", "non_cash",
    "disputed_charge", "receipt_pointer", "solicitation", "no_effect",
}
SERIES_EFFECTS = {
    "not_confirmed",  # only suppresses projection of a variable-income series
    "series_amount_change", "one_time_amount_change", "temporary_amount", "series_starts", "series_ends",
    "occurrence_moved", "confirmed_credit",
}


def load_image_amounts(path: Path) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8"))["images"] if path.exists() else {}


def load_effects(path: Path, ds: Dataset) -> dict[str, list[dict]]:
    """{user_id: [effect + message_id]} restricted to validated, engine-relevant effects."""
    if not path.exists():
        log.warning("no evidence file at %s; running without message evidence", path)
        return {}
    messages = json.loads(path.read_text(encoding="utf-8"))["messages"]
    out: dict[str, list[dict]] = defaultdict(list)
    for message_id, record in sorted(messages.items()):
        user_id = record["user_id"]
        user_pairs = {(e.category, e.direction) for e in ds.events_by_user.get(user_id, [])}
        for effect in record["effects"]:
            kind = effect["type"]
            if kind in NO_ENGINE_ACTION:
                continue
            if kind not in SERIES_EFFECTS:
                log.warning("%s: unknown effect type %s dropped", message_id, kind)
                continue
            if effect["target_kind"] == "series":
                if (effect["category"], effect["direction"]) not in user_pairs:
                    log.warning("%s: series target %s/%s not in ledger; dropped", message_id, effect["category"], effect["direction"])
                    continue
            elif effect["target_kind"] == "event":
                event = ds.events_by_id.get(effect["event_id"] or "")
                if event is None or event.user_id != user_id:
                    log.warning("%s: event target %s not in ledger; dropped", message_id, effect["event_id"])
                    continue
                effect = {**effect, "category": event.category, "direction": event.direction}
            else:
                continue
            out[user_id].append({**effect, "message_id": message_id})
    return dict(out)
