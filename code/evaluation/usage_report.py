"""Generate evaluation/usage_report.md from the committed usage log of the single uncached extraction run.

    python3 code/evaluation/usage_report.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
REPO = CODE.parent
DATA = CODE / "buyorwait" / "evidence" / "data"
EVAL_REQUESTS = 250

# USD per 1M tokens (OpenAI pricing page, fetched 2026-09-13). Reasoning tokens are billed inside output tokens.
PRICING = {
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.50},
}


def _sha(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.relative_to(REPO).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _cost(model: str, prompt: int, cached: int, completion: int) -> float:
    p = PRICING[model]
    return ((prompt - cached) * p["input"] + cached * p["cached_input"] + completion * p["output"]) / 1_000_000


def build() -> str:
    records = [json.loads(line) for line in (DATA / "usage_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    run_ids = sorted({r["run_id"] for r in records})
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_purpose: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        for bucket in (by_model[r["model"]], by_purpose[(r["purpose"], r["model"])]):
            bucket["calls"] += 1
            bucket["prompt"] += r["prompt_tokens"]
            bucket["cached"] += r["cached_prompt_tokens"]
            bucket["completion"] += r["completion_tokens"]
            bucket["reasoning"] += r["reasoning_tokens"]
            bucket["seconds"] += r["seconds"]
    for model, b in by_model.items():
        b["cost"] = _cost(model, int(b["prompt"]), int(b["cached"]), int(b["completion"]))
    total = defaultdict(float)
    for b in by_model.values():
        for k, v in b.items():
            total[k] += v
    tokens = total["prompt"] + total["completion"]

    def row(name: str, b: dict[str, float]) -> str:
        t = b["prompt"] + b["completion"]
        return (f"| {name} | {int(b['calls'])} | {int(b['prompt']):,} | {int(b['cached']):,} | {int(b['completion']):,} | "
                f"{int(b['reasoning']):,} | {int(t):,} | {t / EVAL_REQUESTS:,.1f} | ${b['cost']:.4f} | ${b['cost'] / EVAL_REQUESTS:.5f} |")

    evidence_hash = _sha([DATA / n for n in ("evidence.json", "image_amounts.json", "vocabulary.json", "vocabulary_llm.json", "usage_log.jsonl")])
    engine_hash = _sha([p for p in (CODE / "buyorwait").rglob("*.py")])
    output = REPO / "dataset" / "output.csv"
    output_hash = hashlib.sha256(output.read_bytes()).hexdigest()[:16] if output.exists() else "missing"

    lines = [
        "# Token usage and cost report",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from `buyorwait/evidence/data/usage_log.jsonl`.",
        "",
        "## Which run this describes",
        "",
        f"- **Extraction run:** `{', '.join(run_ids)}`, one uncached pass over the full dataset: every message (215), every image (16), and one vocabulary re-label call. That is {int(total['calls'])} model calls, with 0 failures.",
        "- **How `output.csv` was produced:** the final `dataset/output.csv` came from this run's committed extraction results (`evidence.json`, `image_amounts.json`) plus the calibrated deterministic engine. The engine makes **no model calls**, so re-running `python3 code/main.py` reproduces the file byte for byte without an API key.",
        f"- **Hashes (sha256, truncated):** evidence data `{evidence_hash}`, engine source `{engine_hash}`, `dataset/output.csv` `{output_hash}`.",
        "- **Coverage:** the extraction covers all 275 users (the 250 evaluation users and the 25 sample users). Per-request figures below divide by the 250 evaluation requests.",
        "",
        "## Totals by model",
        "",
        "| Model (provider: OpenAI) | Calls | Input tokens | of which cached | Output tokens | of which reasoning | Total tokens | Avg tokens / request | Est. cost | Est. cost / request |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [row(m, b) for m, b in sorted(by_model.items())]
    lines += [row("**Overall**", total), "", "## Breakdown by job", "",
              "| Job | Model | Calls | Input tokens | Output tokens | Reasoning tokens | Wall seconds (summed) |", "|---|---|---|---|---|---|---|"]
    for (purpose, model), b in sorted(by_purpose.items()):
        lines.append(f"| {purpose} | {model} | {int(b['calls'])} | {int(b['prompt']):,} | {int(b['completion']):,} | {int(b['reasoning']):,} | {b['seconds']:.0f} |")
    lines += [
        "",
        "## Pricing used (USD per 1M tokens)",
        "",
        "| Model | Input | Cached input | Output |",
        "|---|---|---|---|",
    ] + [f"| {m} | {p['input']:.3f} | {p['cached_input']:.3f} | {p['output']:.2f} |" for m, p in PRICING.items()] + [
        "",
        f"Cost = (input − cached) × input rate + cached × cached rate + output × output rate. Reasoning tokens are part of output tokens and are listed separately for visibility, not charged twice. The overall total is **{int(tokens):,} tokens** (about **{tokens / EVAL_REQUESTS:,.0f} per request**), with an estimated **${total['cost']:.2f}** in all (**${total['cost'] / EVAL_REQUESTS:.4f} per request**).",
        "",
        "Settings: Chat Completions with `response_format` strict JSON schema, `seed=7`, `reasoning_effort` `low` for messages and `medium` for images and vocabulary. No API keys or credentials appear in this report.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    out = CODE / "evaluation" / "usage_report.md"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
