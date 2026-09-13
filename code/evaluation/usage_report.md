# Token usage and cost report

Generated 2026-09-13 08:12 UTC from `buyorwait/evidence/data/usage_log.jsonl`.

## Which run this describes

- **Extraction run:** `extract-20260913T075652Z`, one uncached pass over the full dataset: every message (215), every image (16), and one vocabulary re-label call. That is 232 model calls, with 0 failures.
- **How `output.csv` was produced:** the final `dataset/output.csv` came from this run's committed extraction results (`evidence.json`, `image_amounts.json`) plus the calibrated deterministic engine. The engine makes **no model calls**, so re-running `python3 code/main.py` reproduces the file byte for byte without an API key.
- **Hashes (sha256, truncated):** evidence data `ef93d937d65a9a41`, engine source `7432a91c92113ef3`, `dataset/output.csv` `7657fe3daa7894be`.
- **Coverage:** the extraction covers all 275 users (the 250 evaluation users and the 25 sample users). Per-request figures below divide by the 250 evaluation requests.

## Totals by model

| Model (provider: OpenAI) | Calls | Input tokens | of which cached | Output tokens | of which reasoning | Total tokens | Avg tokens / request | Est. cost | Est. cost / request |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5.4 | 17 | 29,386 | 0 | 11,221 | 8,615 | 40,607 | 162.4 | $0.2418 | $0.00097 |
| gpt-5.4-mini | 215 | 328,121 | 3,840 | 42,668 | 23,005 | 370,789 | 1,483.2 | $0.4355 | $0.00174 |
| **Overall** | 232 | 357,507 | 3,840 | 53,889 | 31,620 | 411,396 | 1,645.6 | $0.6773 | $0.00271 |

## Breakdown by job

| Job | Model | Calls | Input tokens | Output tokens | Reasoning tokens | Wall seconds (summed) |
|---|---|---|---|---|---|---|
| image | gpt-5.4 | 16 | 26,844 | 3,885 | 3,211 | 38 |
| message | gpt-5.4-mini | 215 | 328,121 | 42,668 | 23,005 | 435 |
| vocabulary | gpt-5.4 | 1 | 2,542 | 7,336 | 5,404 | 41 |

## Pricing used (USD per 1M tokens)

| Model | Input | Cached input | Output |
|---|---|---|---|
| gpt-5.4 | 2.500 | 0.250 | 15.00 |
| gpt-5.4-mini | 0.750 | 0.075 | 4.50 |

Cost = (input − cached) × input rate + cached × cached rate + output × output rate. Reasoning tokens are part of output tokens and are listed separately for visibility, not charged twice. The overall total is **411,396 tokens** (about **1,646 per request**), with an estimated **$0.68** in all (**$0.0027 per request**).

Settings: Chat Completions with `response_format` strict JSON schema, `seed=7`, `reasoning_effort` `low` for messages and `medium` for images and vocabulary. No API keys or credentials appear in this report.
