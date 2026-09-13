# Buy or Wait?

Deciding, for one user's purchase or payment request, whether and how they can pay it safely within a 90-day forecast.

## Money and time

**Request**:
One user's proposed commitment of a requested amount, with a request date and a deadline.
_Avoid_: purchase, question, query

**Deadline**:
The request's `desired_completion_date`; the last day the full amount may be paid.
_Avoid_: due date, decide-by date

**Forecast window**:
The 90 days that start on the request date. Every safety judgement is made over this window only.
_Avoid_: horizon, rolling window

**Minimum balance**:
The balance the user wants never to go below at any point in the forecast window.
_Avoid_: floor, buffer, reserve

**Low point**:
The lowest projected balance in the forecast window; it caps how much can be paid on a given day.
_Avoid_: trough, minimum (ambiguous with minimum balance)

**Pending reserve**:
A pending debit held back from spendable money until it settles. Pending credits are never counted.
_Avoid_: hold, authorization

**Disputed charge**:
A pending "Possible duplicate card charge" debit that links to a settled charge of the same amount, and that the bank is still investigating with no reversal posted. It is reserved like any pending debit until a reversal posts.
_Avoid_: duplicate charge, duplicate record

## Forecasting

**Recurring series**:
One user's cash flows in one category and direction, regardless of description, repeating at a regular gap (the most common gap covers at least 75% of intervals; 28–31 days counts as monthly) with at least 3 occurrences. Two occurrences are enough only when a scheduled event or a message confirms the series.
_Avoid_: subscription, habit, description series

**Income stream**:
A recurring series of salary credits. Bonuses, commissions, arrears, reimbursements, prizes and sale proceeds are removed before its gap is measured. If the remaining credits are still irregular, they are split by description (e.g. two household earners). Only regular streams are projected; gig and freelance income is variable income.
_Avoid_: salary series, payroll

**Evidence effect**:
One typed consequence extracted from a message (for example `series_ends` or `failed_debit_retry`), aimed at an event or a series the user actually has. Message text never reaches the decision logic; only effects do.
_Avoid_: signal, hint, message instruction

## Plans

**Plan**:
A dated schedule of payments, optionally with spending changes, that completes a request.
_Avoid_: option (reserved for supplied payment options), recommendation

**Payment option**:
A seller-supplied way to pay (full payment or a fixed installment schedule). Installment plans must copy one exactly; partial payments and waits are not payment options.

**Safe plan**:
A plan the user will consider, which finishes by the deadline and never takes the balance below the minimum balance in the forecast window.
_Avoid_: affordable plan, valid plan

**Safe amount**:
The most that can be paid on the request date without spending changes while keeping the balance at or above the minimum balance, capped at the requested amount.
_Avoid_: affordable amount

**Earliest full-payment date**:
The first day in the forecast window on which paying the full amount in one payment is safe without spending changes. It describes capacity, not what the user will accept.

## Spending changes

**Spending change**:
A `stop` or a `reduce_to` applied to a flexible recurring expense to make a plan safe. Used only when no safe plan exists without changes.
_Avoid_: cut, adjustment, saving

**Change target**:
The latest occurrence before the request date of the expense being changed; its `event_id` is what the change names.

**Reduce**:
Lowering a reducible expense to exactly its `minimum_allowed_amount`, in a category the user will reduce and does not protect.

**Stop**:
Removing a stoppable expense entirely, in a category the user will stop and does not protect.

**Protected category**:
A spending category the user will not change. It is still forecast.

## Status

**Affordable now**:
The full amount is safe on the request date and the user accepts full payment.

**Affordable with plan**:
The winning plan is a partial payment, installments, or needs spending changes.

**Affordable later**:
No immediate plan wins, but an earliest full-payment date exists in the forecast window.

**Not affordable**:
No earliest full-payment date exists in the forecast window and no safe plan exists.
