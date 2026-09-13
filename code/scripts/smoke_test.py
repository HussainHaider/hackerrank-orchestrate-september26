"""Gate (plan §3.1): prove the server accepts every Chat Completions parameter we rely on, per model."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buyorwait.config import DATASET_DIR, REPO_ROOT  # noqa: E402
from buyorwait.evidence.client import LLMClient, image_data_url  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"effect": {"type": "string", "enum": ["series_amount_change", "no_effect"]}, "amount": {"type": ["number", "null"]}},
    "required": ["effect", "amount"],
    "additionalProperties": False,
}
IMG_SCHEMA = {
    "type": "object",
    "properties": {"amount": {"type": ["number", "null"]}, "currency": {"type": ["string", "null"]}, "field_used": {"type": "string"}},
    "required": ["amount", "currency", "field_used"],
    "additionalProperties": False,
}

client = LLMClient(REPO_ROOT / ".scratch" / "smoke_usage.jsonl", run_id="smoke")
ok = True
try:
    r = client.structured(
        purpose="smoke", item_id="text", model="gpt-5.4-mini", effort="low",
        system="Extract the payroll effect as JSON.",
        user_content=[{"type": "text", "text": "Your monthly salary increases to EUR 1500 from 2026-02-15."}],
        schema_name="smoke_text", schema=SCHEMA,
    )
    print("gpt-5.4-mini text OK:", json.dumps(r.data), "| usage:", {k: r.usage[k] for k in ("response_model", "prompt_tokens", "completion_tokens", "reasoning_tokens")})
except Exception as exc:  # report and continue so both gates are visible
    ok = False
    print("gpt-5.4-mini text FAILED:", type(exc).__name__, str(exc)[:400])
try:
    r = client.structured(
        purpose="smoke", item_id="image_01", model="gpt-5.4", effort="medium",
        system="Read the payslip image. Return the net pay amount the employee receives.",
        user_content=[{"type": "text", "text": "Return net pay."}, {"type": "image_url", "image_url": {"url": image_data_url(str(DATASET_DIR / "media/images/image_01.png"))}}],
        schema_name="smoke_image", schema=IMG_SCHEMA,
    )
    print("gpt-5.4 image OK:", json.dumps(r.data), "| usage:", {k: r.usage[k] for k in ("response_model", "prompt_tokens", "completion_tokens", "reasoning_tokens")})
except Exception as exc:
    ok = False
    print("gpt-5.4 image FAILED:", type(exc).__name__, str(exc)[:400])
sys.exit(0 if ok else 1)
