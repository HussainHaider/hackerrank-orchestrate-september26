"""The single uncached extraction run (plan §3.2): vocabulary re-label, messages, images.

Writes evidence/data/{evidence.json, image_amounts.json, vocabulary_llm.json, usage_log.jsonl}.
The engine never calls this; it reads the committed files.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from ..contracts import Dataset, Event, Message
from . import prompts, schema
from .client import LLMClient, image_data_url

MESSAGE_MODEL, MESSAGE_EFFORT = "gpt-5.4-mini", "low"
IMAGE_MODEL, IMAGE_EFFORT = "gpt-5.4", "medium"
VOCAB_MODEL, VOCAB_EFFORT = "gpt-5.4", "medium"


def _event_line(e: Event) -> str:
    amount = "blank" if e.amount is None else f"{e.amount:g}"
    link = f" linked={e.linked_event_id}" if e.linked_event_id else ""
    return f"{e.event_id} | {e.settlement_date} | {e.status} | {e.direction} | {e.category} | {e.description} | {amount} {e.currency}{link}"


def _series_summary(events: list[Event], before) -> list[str]:
    groups: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for e in events:
        if e.status == "settled" and e.settlement_date < before and e.direction in ("credit", "debit"):
            groups[(e.category, e.direction)].append(e)
    lines = []
    for (category, direction), es in sorted(groups.items(), key=lambda kv: (kv[0][1] != "credit", kv[0][0])):
        es.sort(key=lambda e: e.settlement_date)
        last = es[-1]
        descriptions = Counter(e.description for e in es).most_common(3)
        lines.append(
            f"{category} | {direction} | {len(es)} rows | last {last.settlement_date} "
            f"{'blank' if last.amount is None else f'{last.amount:g}'} {last.currency} | "
            f"descriptions: {', '.join(d for d, _ in descriptions)}"
        )
    return lines


def message_context(ds: Dataset, m: Message) -> str:
    profile = ds.profiles[m.user_id]
    events = ds.events_by_user.get(m.user_id, [])
    request = next((r for r in ds.requests if r.user_id == m.user_id), None)
    cutoff = request.request_date if request else max(e.settlement_date for e in events)
    linked = ds.events_by_id.get(m.related_event_id) if m.related_event_id else None
    open_events = [e for e in events if e.status != "settled"]
    parts = [
        f"home_currency: {profile.home_currency}",
        f"message sent_at: {m.sent_at} | source_type: {m.source_type}",
        "linked event: " + (_event_line(linked) if linked else "none"),
        "non-settled events:\n" + ("\n".join(_event_line(e) for e in open_events) or "none"),
        "recurring flow summary (settled history):\n" + "\n".join(_series_summary(events, cutoff)),
        "MESSAGE:\n" + m.text,
    ]
    return "CONTEXT\n" + "\n\n".join(parts)


def image_context(ds: Dataset, event_id: str) -> str:
    e = ds.events_by_id[event_id]
    return "CONTEXT\nlinked ledger event: " + _event_line(e) + "\nReturn the amount that settles this event."


def _extract_message(client: LLMClient, ds: Dataset, m: Message) -> tuple[str, dict[str, Any]]:
    result = client.structured(
        purpose="message", item_id=m.message_id, model=MESSAGE_MODEL, effort=MESSAGE_EFFORT,
        system=prompts.MESSAGE_SYSTEM, user_content=[{"type": "text", "text": message_context(ds, m)}],
        schema_name="message_effects", schema=schema.MESSAGE_SCHEMA,
    )
    return m.message_id, {"user_id": m.user_id, "related_event_id": m.related_event_id, "effects": result.data["effects"]}


def _extract_image(client: LLMClient, ds: Dataset, event_id: str) -> tuple[str, dict[str, Any]]:
    ref = ds.images_by_event[event_id]
    result = client.structured(
        purpose="image", item_id=ref.image_id, model=IMAGE_MODEL, effort=IMAGE_EFFORT,
        system=prompts.IMAGE_SYSTEM,
        user_content=[{"type": "text", "text": image_context(ds, event_id)}, {"type": "image_url", "image_url": {"url": image_data_url(ref.path)}}],
        schema_name="image_amount", schema=schema.IMAGE_SCHEMA,
    )
    return event_id, {"image_id": ref.image_id, "user_id": ref.user_id, **result.data}


def _extract_vocabulary(client: LLMClient, ds: Dataset) -> dict[str, str]:
    stats: dict[str, Counter] = defaultdict(Counter)
    for es in ds.events_by_user.values():
        for e in es:
            stats[e.description][f"{e.direction}/{e.category}/{e.status}"] += 1
    listing = "\n".join(f"{d} :: " + ", ".join(f"{k} x{v}" for k, v in c.most_common(2)) for d, c in sorted(stats.items()))
    result = client.structured(
        purpose="vocabulary", item_id="all_descriptions", model=VOCAB_MODEL, effort=VOCAB_EFFORT,
        system=prompts.VOCAB_SYSTEM, user_content=[{"type": "text", "text": listing}],
        schema_name="description_roles", schema=schema.VOCAB_SCHEMA,
    )
    return {entry["description"]: entry["role"] for entry in result.data["entries"]}


def run(ds: Dataset, out_dir: Path, messages: Optional[Iterable[Message]] = None, image_events: Optional[Iterable[str]] = None,
        include_vocabulary: bool = True, workers: int = 8, usage_log_name: str = "usage_log.jsonl") -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("extract-%Y%m%dT%H%M%SZ")
    usage_log = out_dir / usage_log_name
    usage_log.unlink(missing_ok=True)  # the committed log describes exactly one run
    client = LLMClient(usage_log, run_id)
    msgs = list(messages) if messages is not None else [m for ms in ds.messages_by_user.values() for m in ms]
    imgs = list(image_events) if image_events is not None else sorted(ds.images_by_event)

    evidence: dict[str, Any] = {}
    images: dict[str, Any] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_extract_message, client, ds, m): ("message", m.message_id) for m in msgs}
        futures.update({pool.submit(_extract_image, client, ds, ev): ("image", ev) for ev in imgs})
        for fut in as_completed(futures):
            kind, key = futures[fut]
            try:
                k, value = fut.result()
                (evidence if kind == "message" else images)[k] = value
            except Exception as exc:  # keep going; failures are reported and block commit
                failures.append(f"{kind}:{key}: {type(exc).__name__}: {exc}")
    vocab_llm = _extract_vocabulary(client, ds) if include_vocabulary else None

    meta = {"run_id": run_id, "message_model": MESSAGE_MODEL, "image_model": IMAGE_MODEL, "vocabulary_model": VOCAB_MODEL}
    (out_dir / "evidence.json").write_text(json.dumps({"meta": meta, "messages": dict(sorted(evidence.items()))}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "image_amounts.json").write_text(json.dumps({"meta": meta, "images": dict(sorted(images.items()))}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if vocab_llm is not None:
        (out_dir / "vocabulary_llm.json").write_text(json.dumps({"meta": meta, "roles": dict(sorted(vocab_llm.items()))}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"run_id": run_id, "messages": len(evidence), "images": len(images), "failures": failures}
