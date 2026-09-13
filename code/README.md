# Buy or Wait? — financial decision agent

For every request in `dataset/requests.csv`, this decides whether the user should pay in full, pay partially, use installments, wait, or not proceed, and writes `dataset/output.csv`.

The design, and the answers to the planning questions, are in `docs/plan.md` in the repository. Domain terms are defined in `CONTEXT.md`.

## Quick start

```bash
# Python 3.10+. The engine needs no third-party packages.
python3 main.py                                    # 250 requests -> dataset/output.csv (offline, deterministic)
python3 -m pytest tests -q                         # 28 tests
python3 evaluation/score.py --pred <csv>           # per-column score against dataset/sample_requests.csv
```

From the repository root, prefix these paths with `code/`. The dataset is found automatically: it can be `dataset/` beside or above the code, or set with `BUYORWAIT_DATASET=/path/to/dataset`.

Other commands:

```bash
python3 main.py --requests dataset/sample_requests.csv --out /tmp/sample_output.csv   # run the 25 labelled samples
python3 evaluation/tune.py                          # calibration grid over the switches (scored on the samples)
python3 evaluation/usage_report.py                  # regenerate evaluation/usage_report.md
OPENAI_API_KEY=... python3 main.py --extract        # the single uncached LLM extraction run (rewrites evidence data)
```

Put `OPENAI_API_KEY` in the environment or in a git-ignored `.env` at the repository root. It is needed **only** for `--extract`.

## How it works

```
Load CSVs ─► Ledger (statuses, FX, pending reserve) ─► Recurring series ─► 90-day forecast ─► Plans ─► Status ─► Explanation ─► Validate ─► CSV
                                   ▲                                          ▲
               committed LLM evidence: image amounts, message effects, description roles
```

**Deterministic, with no model calls at decision time.**
- **FX:** conversion uses an exact dated rate; a missing rate is an error.
- **Event statuses:**
  - pending debits, including disputed "possible duplicate" charges, are reserved on the request date;
  - pending credits, failed and cancelled rows, and unrealized values are ignored.
- **Recurring series:** one per (category, direction).
  - Monthly series are projected on their usual day of the month (moved to the last day in shorter months); other series step forward by their regular gap.
  - Income is handled in this order:
    1. remove bonuses, commissions and arrears;
    2. apply lifecycle roles (final payroll, a new job, leave pause and resume);
    3. split into same-day-of-month clusters when the income is still irregular (two earners, paydays on the 7th and 20th);
    4. drop streams that have already missed a payment.
  - Variable (gig or freelance) income is projected at a low percentile, unless a message says the payout is pending.
- **Forecast:** a daily end-of-day balance from the request date to request date + 90.
  - Safe amount = low point − minimum balance, capped to [0, requested].
  - Earliest full-payment date = the first day on which a full payment keeps every later end-of-day balance at or above the minimum.
- **Plans:**
  - every plan must use a method the user accepts and finish by the deadline;
  - installments must copy a supplied option, with no more than `max_installment_months` payments;
  - plans that need no spending changes win first;
  - otherwise, full payment or installments are paired with the best **simulated** safe change set (smallest total cut, then fewest changes; at most 3; stop or reduce only where permitted and never in protected categories; named by the latest event in the category);
  - ties are ranked by total paid, then start date, then number of payments, then option id.
- **Status** is read from the winning plan. If nothing qualifies, the status is `affordable_later` when an earliest date exists and `not_affordable` otherwise.
- **Explanations** use the template shapes found in the labelled samples.
- **A validator** checks every output contract rule before anything is written.

**LLM, used once and committed.** These results are stored in `buyorwait/evidence/data/`:

| Job | Model | Output |
|---|---|---|
| 215 messages → typed evidence effects (closed enum, list per message) | `gpt-5.4-mini` | `evidence.json` |
| 16 images (payslips, invoices) → the amount for their blank-amount event | `gpt-5.4` (vision) | `image_amounts.json` |
| 164 descriptions → cash-flow role (cross-check) | `gpt-5.4` | `vocabulary_llm.json` |

All calls use Chat Completions with a strict JSON schema, `seed=7`, and `reasoning_effort` set to low or medium. Every call is logged to `usage_log.jsonl`.

**Treating message and image text as untrusted:**
- The engine only reads enum and number fields, never the text.
- An effect that points at an event or series outside the user's own ledger is dropped.
- A request to pay a fee to release a prize (message_67) is classified `solicitation` and has no effect.
- `request_text` is not used: its facts duplicate the structured columns (all 275 rows agree).

**Description roles** (`vocabulary.json`) come from reviewed keyword rules over the closed set of 164 descriptions, so the engine never waits on the API. The LLM re-label disagreed on 7 descriptions:
- 5 disagreements are artifacts: the LLM run was given the role list from before the `known_future` / `known_extra` split.
- **"August 2019 net salary"** (LLM: one-off): kept as recurring, because it is a regular monthly payslip.
- **"Card charge later reversed"** (LLM: disputed): kept as one-off, because it is a settled charge with a posted reversal.

The keyword rules stay authoritative.

## Reproducibility

`python3 main.py` is deterministic: the same inputs and committed evidence give byte-identical output, with no network and no key. The only nondeterministic step is `--extract`, and its results are committed. `evaluation/usage_report.md` describes that run and records the hashes of the evidence, the engine and `output.csv`.

## Calibration (25 labelled samples)

The tuned switches are in `buyorwait/config.py`: `expense_estimator=mean` over 6 recent occurrences, end-of-day balance checks, `pending_in_balance=False`, and variable income at the 25th percentile. Each switch is a reading of the spec, not a fitted constant, and the grid is in `evaluation/tune.py`.

Current sample scores (`evaluation/score.py`):

| status | method | payment plan | earliest date | spending changes | explanation template | safe amount within 1% |
|---|---|---|---|---|---|---|
| 0.76 | 0.80 | 0.76 | 0.68 | 0.84 | 0.68 | 0.16 (median abs. % error 0.09) |

## Layout

```
main.py                  entry point
buyorwait/               config, contracts, loaders, fx, vocabulary, ledger, recurrence, forecast, planner,
                         explain, formatting, validate, pipeline, context
buyorwait/evidence/      client (OpenAI), prompts, schema, extract (the one uncached run), apply; data/ (committed)
evaluation/              score.py, tune.py, usage_report.py, usage_report.md
tests/                   pytest suite (ledger rules, projection, evidence safety, planner, formats, validator)
scripts/                 smoke test, extraction trial, capacity debug helpers
```

## Known limitations

- The safe amount matches the samples exactly in only a few cases. The amount estimate for variable categories is the main source of error, and there are only 25 labels to calibrate against.
- Two combinations have no sample to copy an explanation from (`affordable_later` + `not_recommended`, and installments with spending changes), so their templates are this project's own wording.
