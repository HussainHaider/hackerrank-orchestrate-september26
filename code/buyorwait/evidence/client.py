"""Thin OpenAI Chat Completions wrapper: strict JSON schema output + per-call usage logging.

Only Chat Completions parameters are used (plan §3.1): response_format json_schema strict,
reasoning_effort, seed. Credentials come from the environment or the repo-root .env.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..config import REPO_ROOT

SEED = 7


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    """Populate os.environ from KEY=VALUE lines without overriding existing variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def image_data_url(path: str) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


@dataclass
class CallResult:
    data: dict[str, Any]
    usage: dict[str, Any]


class LLMClient:
    def __init__(self, usage_log: Path, run_id: str):
        load_env()
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set (export it or add it to the repo-root .env)")
        from openai import OpenAI  # imported lazily so the offline engine never needs the SDK

        self._client = OpenAI(max_retries=4, timeout=180)
        self._usage_log = usage_log
        self._run_id = run_id
        self._lock = threading.Lock()

    def structured(
        self,
        *,
        purpose: str,
        item_id: str,
        model: str,
        effort: str,
        system: str,
        user_content: list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
    ) -> CallResult:
        started = time.time()
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_content}],
            response_format={"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            reasoning_effort=effort,
            seed=SEED,
        )
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise RuntimeError(f"{purpose}/{item_id}: model refused: {choice.message.refusal}")
        data = json.loads(choice.message.content)
        usage = self._record(purpose, item_id, model, effort, response, time.time() - started, choice.finish_reason)
        return CallResult(data=data, usage=usage)

    def _record(self, purpose, item_id, model, effort, response, seconds, finish_reason) -> dict[str, Any]:
        u = response.usage
        prompt_details = getattr(u, "prompt_tokens_details", None)
        completion_details = getattr(u, "completion_tokens_details", None)
        record = {
            "run_id": self._run_id,
            "purpose": purpose,
            "item_id": item_id,
            "model": model,
            "response_model": response.model,
            "reasoning_effort": effort,
            "prompt_tokens": u.prompt_tokens,
            "cached_prompt_tokens": getattr(prompt_details, "cached_tokens", 0) or 0,
            "completion_tokens": u.completion_tokens,
            "reasoning_tokens": getattr(completion_details, "reasoning_tokens", 0) or 0,
            "system_fingerprint": response.system_fingerprint,
            "finish_reason": finish_reason,
            "seconds": round(seconds, 2),
        }
        with self._lock:
            self._usage_log.parent.mkdir(parents=True, exist_ok=True)
            with self._usage_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        return record
