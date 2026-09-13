# Buy or Wait? — Architecture & Build Plan (rev 4)

Status: **rev 4, design complete; implementation starting.** Rev 4 applies the third review (§0.0). Where rev 4 and rev 3 disagree, rev 4 wins.
Deadline: 2026-09-13 18:00 IST. About 4h40m remained when this revision was written.
Terms follow `CONTEXT.md`: low point, safe plan, change target, and so on.

---

## 0. What changed

### 0.0 Rev 4: third review and Q14–Q17 (checked against the data)

| Item | Verdict | Change |
|---|---|---|
| Duplicate rule and dispute rule both apply to all 6 duplicate rows | Correct. All 6 rows are "Possible duplicate card charge", every one has a bank message saying *"the extra card charge is still being investigated, no reversal posted"*, all 6 belong to evaluation users, and the data has no other duplicates of any kind | **Q15 (a): these charges are reserved.** They are treated as disputed charges, not duplicate records. The "duplicates are not reserved" rule is removed |
| internal_transfer has nothing to pair with | Correct. For all 5 users (user_18/33/57/171/261), no debit and credit share an amount and date, and the messages have no related_event_id | **Q16: the engine does nothing with it.** The pairing rule is removed; the type stays so extraction still classifies these messages. user_18 is a test case |
| Monthly projection drifts off payday | Correct. Monthly gaps are 31/30/29/28 days. **No** series has only 28-day gaps, and all 1,821 series with monthly gaps have a stable day of the month | Monthly series are projected **on their day of the month, moved to the last day in shorter months**. Stepping by the gap applies only to 5/7/10/14/21-day series |
| Stage B ranking breaks spec order | Correct. 56 evaluation users accept both full_payment and installments | **Q14: spec order.** Each schedule gets its best change set, then schedules are ranked by total paid, start date, number of payments and option id |
| Vocabulary would block the engine | Correct in principle. The key is now set (`.env`, 164 chars, gitignored) | **Q17:** a deterministic keyword vocabulary is written first and committed. The LLM re-labels the same strings later, and its result is committed only after a reviewed diff |
| failed_debit_retry would never add the debit back | Correct. All 4 messages link to a scheduled retry event with the same amount | Match on `linked_event_id`. The scheduled retry is counted once and never added back a second time |
| Step 4 of the income rules says "latest" and also "low percentile" | Correct | Use the **lower** of the latest amount and the low percentile |
| Extraction run "writes output.csv using whatever engine exists" | Correct | Clause removed |
| minimum_allowed_amount is the same across a category | Confirmed: 349 of 349 user/category groups have a single value | No change; targeting by category is safe |


### 0.1 Rev 3: the second-review findings

| Finding | Verdict (re-checked against the data) | Section |
|---|---|---|
| event_989 belongs to a regular dining series, not a 2-occurrence one | **Correct, and it goes further.** Across the 275 users, every expense category except shopping is 100% regular at the (category, direction) level: groceries run every 7/10/14 days, transport every 5/7/14/21, dining every 7/14/21, and bills monthly. Shopping is 137 of 142. The idea from rev 1 that some spending is "jittered" and irregular was wrong for every category | §4.3 |
| Change targets are the latest event in the category | Correct for all 4 samples. user_11 has 9 dining charges at 21-day gaps, and event_989 is the last of them | §5.3 |
| "However savings are counted" only holds when safety is simulated | Correct. Stopping event_1815 saves 3 × 11 = 33, which covers the gap, but only one of those charges comes before the low point. Every change set is run through `plan_is_safe`, and the plan never checks "savings ≥ gap" | §5.3 |
| Pending debits settle 1–7 days after the request date | Correct: 13 settle at +1 day, 15 at +2, 20 at +3, 14 at +4, 1 at +6, 8 at +7 | §4.2 |
| The rolling safety window can't run | Correct. Within the 90-day window, 0 projected foreign-currency flows lack an FX rate; days 91–180 would lack 33, across 12 users. All FX rates fall on the 15th of the month | §5.1 (switch removed, Q11) |
| Message evidence types are undefined | Correct, but **Q10's list is incomplete**. See §3.3 | §3.3 |
| Evidence is refreshed after calibration | Correct, fixed per Q12 | §3.2, §9 |
| Status-table gap | Correct. Q13 adds an explicit row | §5.4 |
| Missing explanation templates | Correct; 2 templates added | §5.5 |
| No API smoke test | Correct; it is a gate in §9 | §7, §9 |
| No look-ahead leakage | Confirmed: no message is sent after its request date, every full_payment option has the request's date and amount, and no installment starts before the request date | — |

**Correction to rev 2 §0 row 15.** Rev 2 said there was no injection text in messages. That is true of `request_text` but **false for messages**. The earlier check searched for prompt-injection wording and missed social engineering. **message_67** (user_88, an evaluation user) says: *"You've been selected for a cash prize. Pay the release charge today to receive the funds immediately."* It must produce **no effect**: no prize income and no "release charge" expense.

### 0.2 Decisions

| Q | Verdict |
|---|---|
| Q9 What a recurring series is | **Agree for expenses. Income needs more rules**, because **72 of 252** salary series are irregular at the (category, direction) level. The causes are identifiable from the descriptions: a bonus in the salary category (10), two household earners in one category (10), leave gaps (9), base pay plus commissions (9), gig payouts (5), freelance projects (≥9), and a payroll date moved once (8). The rule is in §4.3 |
| Q10 Evidence types | **Agree, with additions.** Five templates are missing and two fields are needed. See §3.3 |
| Q11 Drop the rolling window | **Agree.** The fixed window is now the rule |
| Q12 When to run extraction | **Agree with (a), and run it earlier.** Extraction doesn't depend on the engine, so it runs uncached as soon as the smoke test passes, and no later than 15:10 |
| Q13 Status when full payment is safe but not accepted | **Agree:** `affordable_later`, earliest date = request date |
| Q4 reversal plus the simulation caveat | Accepted. Selection is: simulate, keep the sets that pass, then rank by smallest cut |

### 0.3 Carried over from rev 2

The deadline is a filter. Stop and reduce have separate permissions. Duplicates are found via `linked_event_id`. Known events replace projected occurrences within the same pay cycle. Only Chat Completions is used. Output goes to `dataset/output.csv`, and `--requests` selects which requests to run. The work is one stream. `financial_priorities` and `request_text` are deliberately unused.

---

## 1. Data facts

| Input | Rows | Notes |
|---|---|---|
| `requests.csv` | 250 | request_26–275, one per user; 170 don't allow partial payment |
| `sample_requests.csv` | 25 | request_01–25, labelled; no users in common with `requests.csv` |
| `financial_profiles.csv` | 275 | INR 67, EUR 62, IDR 55, ZAR 51, USD 40; 119 have a blank `max_installment_months` |
| `financial_events.csv` | 25,342 | 164 distinct descriptions (complete, nothing hidden) |
| `exchange_rates.csv` | 134 | 133 rates on the 15th of the month, 1 on the 1st; every rate needed inside the window exists |
| `request_payment_options.csv` | 790 | full_payment 275, installments 515 (2–24 payments at 28/30/31-day intervals; 81 finish by the deadline) |
| `messages.csv` | 215 | at most one per user, 60 users have none; 128 tied to a request, 87 general, 39 tied to an event |
| `images.csv` | 16 | exactly the 16 events with a blank amount |

**What falls inside the window:**
- **Scheduled events:** 68 of 70 are on or after the request date.
- **Pending events:** all 71 have an event date before the request date and settle 1–7 days after it.
- **Everything else is projected** from recurring series.

**Formula:**
`amount_safe_to_pay = clamp(low_point(no payment) − minimum_balance, 0, requested_amount)`.

**Probe:** a rough forecaster came within 1–16% on two-thirds of the 21 uncapped samples. The 5 outliers each map to a rule in §4.

---

## 2. Deterministic core vs. LLM

| Concern | Approach |
|---|---|
| FX, statuses, duplicates, internal transfers, recurrence, simulation, safe amount, earliest date, filters, ranking, spending changes, status, explanations, validation | **Deterministic** |
| Role of each of the 164 descriptions | **LLM, one call**, result committed |
| 215 messages → a list of typed effects | **LLM, one call each** |
| 16 images → amounts | **LLM vision, one call each** |

That is 232 calls. The model never does arithmetic: percentages and currency conversion are applied by the engine.

---

## 3. LLM layer

### 3.1 API (checked against SDK 2.37.0)

Chat Completions only, with:
- `response_format` set to `json_schema` with `strict: true`
- `reasoning_effort`: `low` for messages, `medium` for vocabulary and images
- `seed=7`
- images sent as base64 `image_url` data URIs

Usage fields read:
- `prompt_tokens`
- `completion_tokens`
- `prompt_tokens_details.cached_tokens`
- `completion_tokens_details.reasoning_tokens`

**Smoke test (gate):** one message call on `gpt-5.4-mini` and one image call on `gpt-5.4`, each using every parameter above together. If the server rejects a parameter, drop it and record that in the README. The type hints alone don't prove the server accepts them.

### 3.2 Committed evidence and the usage report (Q12)

- **Files committed** to `code/buyorwait/evidence/data/`:
  - `vocabulary.json`
  - `evidence.json`
  - `image_amounts.json`
  - `usage_log.jsonl`
- `.cache/` is only for local development.
- **The one uncached extraction run happens as early as possible, and by 15:10 at the latest.** It makes all 232 calls and writes the four files. Every later run, including calibration and the final run, reads these files and never calls the API again.
- **`evaluation/usage_report.md` is generated from that run's `usage_log.jsonl`.** It states that the final `output.csv` came from this run's extraction plus the calibrated engine, and gives the sha256 of `evidence/data/` and the engine's git tree.
- Re-extracting is allowed only before calibration starts.

### 3.3 Message effects (Q10, extended)

**Shape of the output.** Extraction returns **a list of effects**, not one type. message_86 needs two: a receipt pointer and a confirmed USD 1,296 salary on 2026-09-15.

**Fields.** Each effect has:
- `type`
- `target` (an `event_id`, or a `series: {category, direction}`)
- `amount?`, `percent?`, `currency?`
- `date?`, `until?`
- `quote`

| Type | Template | Engine action |
|---|---|---|
| `series_amount_change` | salary raised from a date; **rent up by N% at renewal** | new series amount from `date` (or from the next occurrence). **A percentage is applied by the engine** |
| `one_time_amount_change` | next salary reduced once | changes one projected occurrence |
| `temporary_amount` | temporary/reduced pay that "continues for the next payroll" (10 messages, none with an end date); temporary pay until a date | amount replaced until `until`. **`until` null → replaced for the whole window** (no restoration without evidence: safer reading) |
| `series_starts` | first salary on a date | starts the series (allows a 2-occurrence series, e.g. request_15) |
| `series_ends` | seasonal contract ended; one of several jobs ended | stops projection from `date`. With several streams, it targets the one named |
| `occurrence_moved` | salary moved to a new date | moves the matching occurrence, which replaces the scheduled date |
| `confirmed_credit` | invoice approved for a date; confirmed foreign salary | adds a credit on `date`, converted at that date's rate |
| `not_confirmed` | bonus/commission not approved; prize still being paid; **refund initiated, not received**; payout pending | the credit is never counted |
| `already_settled` | prize received; sale proceeds settled | never projected again |
| `failed_debit_retry` | *"previous debit attempt failed… another debit will be attempted"* (4 messages) | confirms the linked scheduled retry. It is counted **once**, matched on `linked_event_id`. A failed debit is added back only if no linked retry exists, which is 0 of 4 in this data |
| `internal_transfer` | *"matching debit and credit came from a transfer between your two accounts"* (5 messages, no event_id) | **nothing** (Q16). The transactions it describes aren't in the ledger |
| `non_cash` | portfolio value changed | nothing |
| `disputed_charge` | extra card charge under investigation, no reversal posted (6 messages, one per duplicate row) | the linked pending debit **is reserved** (Q15). It is released only by a posted reversal, and none exists |
| `receipt_pointer` | *"the receipt has the final amount"* (3 messages) | nothing; the amount comes from the image |
| `solicitation` | pay a fee to release a prize (message_67) | **nothing**, logged as untrusted |
| `no_effect` | anything else | nothing |

**Safety rules for evidence:**
- An `event_id` target must be in the user's own ledger.
- A `series` target must be a series the user actually has.
- Any other effect is dropped and logged.

**Precedence (spec order):**
1. An explicit cancellation, settlement or amendment (a message effect)
2. A newer record from the same source
3. A scheduled or settled event
4. A projection

If a conflict remains, take the safer reading.

---

## 4. Rebuilding the ledger

### 4.1 FX

Amounts are converted at load time using the exact rate for (settlement_date, from, to). A missing rate raises an error. Inside the fixed window no rate is missing.

### 4.2 Statuses

| Status | Treatment |
|---|---|
| `settled` | history |
| `scheduled` | a known flow on its settlement date |
| `pending` debit | reserved. By default it is subtracted on the request date (switch `pending_in_balance`). Settlement is 1–7 days after the request date |
| `pending` credit | ignored |
| `cancelled` / `failed` | excluded. A failed debit's retry is counted through its linked scheduled event |
| `unrealized` / `non_cash` | excluded |

**Special cases:**
- **Disputed charges:** "Possible duplicate card charge" rows are pending debits linked to a settled original. **They are reserved**, because the bank says no reversal has been posted (Q15). The data has no other duplicates.
- **Internal transfers:** no engine action (Q16).
- **Linked lifecycles:** a scheduled retry linked to a failed debit counts once; a reversal linked to a charge cancels it.
- **Known events vs. projections:** a scheduled event, or one confirmed or moved by a message, replaces the projected occurrence of the same series within half a cadence.
- **Blank amounts** come from `image_amounts.json`, never 0.

### 4.3 Recurring series (Q9, extended)

**Expenses** use one series per (user, category, direction), whatever the description. A series is regular when the most common gap covers at least 75% of intervals (28–31 days count as one monthly gap) and it has at least 3 occurrences. **Monthly series are projected on their usual day of the month, moved to the last day in shorter months.** Only 5/7/10/14/21-day series step forward from the last occurrence by the gap. The amount is the switch `expense_percentile` over recent occurrences. Irregular expense series are rare (shopping, 5 cases) and are projected at their observed average rate, so spending is never under-projected.

**Income** is where the plain rule breaks (72 of 252 series are irregular). The steps, in order:

1. **Remove one-off and unconfirmed rows** before measuring the cadence, using vocabulary roles. That covers bonuses, commissions, arrears, reimbursements, prizes and sale proceeds. The spec says these don't count until they settle and are never projected.
2. **Mark leave gaps:** `pauses_series` and `resumes_series` rows mark the pause, and the cadence is measured on the current segment.
3. **Split by description** when the remaining series is still irregular, for example "Primary household salary" and "Second household income". Measured: splitting alone makes 33 of the 72 regular.
4. **Project only regular salary streams**, on their day of the month. The amount is the **lower of** the latest occurrence (which reflects raises and cuts, as with user_06 going from 1441 to 1037.52) and a low percentile of recent occurrences.
5. **Variable income** (gig and freelance roles, where cadence and amounts drift): switch `variable_income`. Default `none`, meaning it is not projected; the alternative is a low percentile. request_10's label (safe 12,700 on 524,755 of headroom) suggests `none`.
6. **Vocabulary source (Q17):** `vocabulary.json` starts as **deterministic keyword rules** over the 164 descriptions ("Final", "First-job", "before leave", "bonus", "commission", "Pending", "Failed", "Possible duplicate", …), committed so the engine never waits on the API. The LLM re-labels the same 164 strings; that result replaces the rules only after a reviewed diff, which is recorded in the README.
7. **Lifecycle roles:**
   - `terminates_series` stops the stream; nothing restarts it without a scheduled event or a message.
   - `starts_series` plus a message or scheduled confirmation allows 2 occurrences (request_15).

---

## 5. Decision layer

### 5.1 Primitives and filters

- `max_safe_today()` searches for the largest amount that keeps the low point at or above the minimum balance, capped at the requested amount, with no spending changes.
- `earliest_full_payment_date()` scans each day d from the request date to request date + 90 and returns the first day where the full payment is safe over [d, request date + 90]. **The window is fixed** (Q11). In the labels, 13 of the 14 non-request dates fall on the 15th of the month, which is only a sanity check.
- `plan_is_safe(schedule, changes)` runs the simulation.

**A safe plan must pass all of these:**
1. The user accepts the method (`wait` also requires that they accept `full_payment`).
2. **It finishes by the deadline.**
3. Installments copy a supplied option, with `number_of_payments ≤ max_installment_months`; a blank means no installments.
4. A partial payment needs `allows_partial_payment`, 0 < safe amount < requested amount, and exactly 2 payments.
5. `plan_is_safe` passes.

### 5.2 Choosing a plan in two stages

- **Stage A, no changes:** full payment today, wait, partial payment, and each installment option. Rank by total paid, then earliest start, then fewest payments, then lowest option id.
- **Stage B, only if Stage A is empty:** full payment today and each installment option. **Each schedule gets its best safe change set** (§5.3). If a schedule has none, it drops out. The schedules that remain all tie on the spec's yes/no rule 2, so they are **ranked in spec order: total paid, start date, number of payments, option id** (Q14).

All 3 change samples come out as full payment + `affordable_with_plan`, with the earliest date after the deadline and the safe amount below the request.

### 5.3 Spending changes

**Target.** The **category's** series, named by the latest event in that category before the request date.

**Permissions:**
- **Stop:** `flexibility ∈ {stoppable, reducible_or_stoppable}`, and the category is on the stop list and not protected.
- **Reduce:** `flexibility ∈ {reducible, reducible_or_stoppable}`, the category is on the reduce list and not protected, and the event has a `minimum_allowed_amount`. The new amount is that minimum, applied to every projected occurrence in the window.

**Constraints.** At most 3 changes, and no stop and reduce on the same series.

**Selection:**
1. List every valid set of 1–3 changes.
2. **Keep only the sets where `plan_is_safe` passes.** Never test "savings ≥ gap".
3. Rank by smallest total projected cut over the window, then fewest changes, then lowest event_ids.

`change_order` stays as a switch because request_11 can't settle it until the forecast is calibrated. **request_21 is a fixed test case.**

### 5.4 Status (adds the Q13 row)

| Winning result | Status | Earliest date |
|---|---|---|
| full payment today, no changes | `affordable_now` | request date |
| full payment today + changes | `affordable_with_plan` | computed |
| partial payment / installments (± changes) | `affordable_with_plan` | computed |
| wait | `affordable_later` | computed |
| not_recommended, earliest date exists (including = request date when full payment isn't accepted) | `affordable_later` | computed |
| not_recommended, no earliest date | `not_affordable` | empty |

### 5.5 Output

**Number formats:**
- `amount_safe_to_pay` is written raw (`603.3`).
- Amounts in `payment_plan` and `reduce_to` use 2 decimals when fractional and none when whole (`620.40`, `23.50`, `665950`).

**Explanations** use the 7 templates found in the samples, plus 2 new ones:
- *affordable_later + not_recommended:* "Do not pay now. The full CUR X becomes safe on DATE, but {that is after DATE_deadline | full payment is not a method you accept}."
- *installments + changes:* "Use N installments of CUR X, starting DATE, after {stopping/reducing …}. This leaves at least CUR MIN available."

**Validation.** The validator gates every write.

---

## 6. Evaluation

A custom scoring script runs against the 25 samples, per column: exact match, within 1%, and mean absolute percentage error for amounts; accuracy and a confusion matrix for status and method; exact match for plans and dates plus days off; set equality for changes; template match for explanations.

**The 4 calibration switches:**

| Switch | Default | Alternative |
|---|---|---|
| `pending_in_balance` | False | True |
| `change_order` | min_cut | fewest |
| `expense_percentile` | high | small grid |
| `variable_income` | none | low percentile |

**Out of scope:** leave-one-out, promptfoo, variance runs. A model comparison (gpt-5.4 vs. mini on messages, one run each) happens only if time is left.

---

## 7. Models and cost

| Job | Model | $/1M in · cached · out |
|---|---|---|
| vocabulary (1), images (16) | `gpt-5.4` | 2.50 · 0.25 · 15.00 |
| messages (215) | `gpt-5.4-mini` | 0.75 · 0.075 · 4.50 |

**Estimate:** under $1.50 in total. Reasoning tokens get their own line in the report.

**Key:** `OPENAI_API_KEY` in a gitignored `.env`. **It is not set yet; it is needed by 13:50 for the timeline in §9.**

---

## 8. Layout, CLI, tests

```
code/main.py
code/buyorwait/  contracts config loaders fx ledger recurrence forecast planner changes status explain validate writer
                 evidence/ schema client vocab messages images apply usage   evidence/data/ (committed)
code/evaluation/ score.py usage_report.py usage_report.md
code/tests/
```

```bash
python3 code/main.py                                                    # dataset/output.csv, offline
python3 code/main.py --requests dataset/sample_requests.csv --out .scratch/sample_output.csv
python3 code/evaluation/score.py --pred .scratch/sample_output.csv
python3 code/main.py --extract                                          # the single uncached extraction run
python3 -m pytest code/tests
```

**Test fixtures:**
- USD→IDR salary (user_25)
- disputed duplicate reserved (event_12709)
- internal transfer changes nothing (user_18, a sample user)
- failed debit plus linked retry counted once (user_91)
- monthly projection stays on the 15th across 31-day months
- Stage B ranking in spec order
- a category series with rotating descriptions (user_11 dining)
- splitting two household salaries (request_13)
- bonus removal
- a leave pause
- request_21 change selection
- every row of the status table
- number formats
- every validator rule
- message_67 producing no effect

---

## 9. Timeline (one work stream)

| IST | Step | Gate |
|---|---|---|
| 13:45–14:05 | contracts, loaders, FX, **keyword vocabulary**, tests | all files load |
| 14:05–14:30 | evidence client, schemas, prompts, **smoke test** → **start the uncached extraction in the background** | smoke test passes (key is set) |
| 14:30–15:10 | ledger, recurrence, forecast, tests | **first sample score**; extraction files committed |
| 15:10–15:40 | apply evidence; planner, changes, status, explanations, validator, writer | **first valid 250-row `output.csv`** |
| 15:40–16:40 | calibration switches | configuration frozen |
| 16:40–17:10 | final offline run, usage report, README, zip | deliverables exist |
| 17:10–17:40 | buffer | **submit by 17:40** |

**Change from rev 2:** the first valid output.csv moves from 15:10 to 15:40, because the extraction code now has to be written before the engine.

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Forecast calibration, especially income | High | Rules in §4.3; sample score at 15:10; 4 switches |
| Overfitting 25 samples | High | Every switch is a reading of the spec, not a fitted constant |
| Evidence types wrong or missing | Medium | Effects returned as a list; `no_effect` fallback; unknown targets dropped and logged |
| Key not accepted by the server | Medium | Key is set; the smoke test at 14:05 checks it. The keyword vocabulary keeps the engine unblocked |
| Time | High | Valid file by 15:40; the model comparison is optional |

---

## 11. Implementation deltas (measured during the build; these override earlier sections)

| Plan said | Built | Evidence |
|---|---|---|
| Check balances after the day's debits, before its credits | **End-of-day balance** (credits and debits of the same day net out) | Exact earliest-date matches on the samples went from 8 to 18 of 25. Salary on the 15th can fund a payment on the 15th, which matches 13 of 14 labels |
| Income amount = lower of the latest occurrence and a low percentile | **Low percentile (p25) of the last 6** | With the old rule, one reduced month became the permanent level (request_08) |
| Split irregular income by description | **Split by day-of-month cluster first** (±3 days), then by description | Freelance paid on the 7th and 20th (user_09), gig paid on the 4th/11th/18th/25th (user_10), two earners on the 15th and 20th |
| (not planned) | **Income series that already missed an expected payment before the request date are not projected** | request_13's second income stopped after January |
| A pause ends the stream | A pause followed by a resume **keeps** the stream; monthly detection accepts a stable day of month across a gap | request_14 (leave from March to June) |
| `variable_income` default `none` | **Default `low_percentile`**; a `not_confirmed` message about that variable stream turns projection off | request_09 only fits the label with income projected; request_10's pending-payout message fits no projection |
| One `known_future` role | **`known_future`** (replaces the projected occurrence) vs **`known_extra`** (added on top: bill retries, outstanding balances, one-off bills) | Treating a retry as a replacement would cancel that month's bill |
| `temporary_amount` until a date | `until` null means **the rest of the window** | 10 messages say "temporary pay… continues for the next payroll" and give no end date |
| Expense estimate `high` | **Mean of the last 6 occurrences** | Best on status, method and plan in `evaluation/tune.py`; the grid is flat within one row of 25 |
| Pending charges might double-count with projections | They are added on top | 0 of 57 pending debits fall on their category's cadence |

Scores on the samples at this point: status 0.76, method 0.80, plan 0.76, earliest date 0.68, spending changes 0.84, explanation template 0.68, safe amount within 1% 0.16.
