"""Cash-flow role of each event description (plan §4.3 step 6, Q17).

The description set is closed (164 strings), so roles come from ordered keyword rules and are
committed as ``evidence/data/vocabulary.json``. An LLM re-label may replace this file only after a
reviewed diff. Status (pending/scheduled/failed/...) is handled by the ledger, not here; a role only
says how a description behaves for recurrence and projection.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Roles
RECURRING = "recurring"                    # routine flow; projected if its series is regular
ONE_OFF = "one_off"                        # never projected, excluded from cadence measurement
INCOME_ENDS = "income_ends"                # last row of a stream (e.g. final payroll)
INCOME_ENDED_STREAM = "income_ended_stream"  # history of a stream that no longer pays
INCOME_STARTS = "income_starts"            # first row(s) of a new stream
INCOME_PAUSE = "income_pause"
INCOME_RESUME = "income_resume"
VARIABLE_INCOME = "variable_income"        # gig / freelance / seasonal; switch-controlled
TEMPORARY_INCOME = "temporary_income"      # projected only up to a message-confirmed end date
UNCONFIRMED_INCOME = "unconfirmed_income"  # bonuses, commissions, arrears: never projected (spec)
KNOWN_FUTURE = "known_future"              # scheduled occurrence of a series: replaces that projected occurrence
KNOWN_EXTRA = "known_extra"                # scheduled/outstanding item on top of the series (retry, arrears, one bill)
PENDING_CHARGE = "pending_charge"
DISPUTED_CHARGE = "disputed_charge"
CANCELLED_AUTH = "cancelled_authorization"
FAILED_DEBIT = "failed_debit"
NON_CASH = "non_cash"

ROLES = frozenset({
    RECURRING, ONE_OFF, INCOME_ENDS, INCOME_ENDED_STREAM, INCOME_STARTS, INCOME_PAUSE, INCOME_RESUME,
    VARIABLE_INCOME, TEMPORARY_INCOME, UNCONFIRMED_INCOME, KNOWN_FUTURE, KNOWN_EXTRA, PENDING_CHARGE,
    DISPUTED_CHARGE, CANCELLED_AUTH, FAILED_DEBIT, NON_CASH,
})

# (direction, pattern, role) — first match wins. direction "*" matches any.
RULES: list[tuple[str, str, str]] = [
    ("non_cash", r".", NON_CASH),
    ("*", r"portfolio valuation", NON_CASH),
    # lifecycle and status-flavoured strings
    ("*", r"^possible duplicate", DISPUTED_CHARGE),
    ("*", r"^pending ", PENDING_CHARGE),
    ("*", r"^(cancelled .*authorization|card authorization)$", CANCELLED_AUTH),
    ("*", r"^failed ", FAILED_DEBIT),
    ("*", r"^scheduled bill payment retry$|^outstanding |^hospital bill payable$|^large .*invoice", KNOWN_EXTRA),
    ("*", r"^(next confirmed salary|scheduled )", KNOWN_FUTURE),
    # income streams
    ("credit", r"^final employer payroll$", INCOME_ENDS),
    ("credit", r"^previous employer payroll$", INCOME_ENDED_STREAM),
    ("credit", r"^(first-job payroll|new employer payroll|prorated first salary)$", INCOME_STARTS),
    ("credit", r"before leave", INCOME_PAUSE),
    ("credit", r"after returning from leave", INCOME_RESUME),
    ("credit", r"bonus|commission|arrears", UNCONFIRMED_INCOME),
    ("credit", r"prize|sale proceeds|reimbursement|reversal|refund", ONE_OFF),
    ("credit", r"platform payout|app earnings|marketplace payout", VARIABLE_INCOME),
    ("credit", r"project payment|contract payment|milestone payment|retainer payment|invoice payment|independent work", VARIABLE_INCOME),
    ("credit", r"seasonal|peak-season", VARIABLE_INCOME),
    ("credit", r"^temporary assignment", TEMPORARY_INCOME),
    ("credit", r"payroll|salary|household income", RECURRING),
    # one-off expenses (single purchases, invoices, charge lifecycles) inside routine categories
    ("debit", r"tax invoice|maintenance invoice|bill due$", ONE_OFF),
    ("debit", r"^(airline ticket purchase|taxi fare|pharmacy purchase|tote bag order|ev charging wallet payment)$", ONE_OFF),
    ("debit", r"^(bulk groceries and pantry purchase|delivered grocery order)$", ONE_OFF),
    ("debit", r"later reversed|awaiting refund|^original card charge$|^settled card purchase$|^reimbursable work expense$", ONE_OFF),
]

# Routine expense strings that fall through to RECURRING by design (checked by tests).
DEFAULT_ROLE = RECURRING


def classify(description: str, direction: str) -> tuple[str, bool]:
    """Return (role, matched_by_rule). ``matched_by_rule`` is False for the default."""
    text = description.strip().lower()
    for rule_direction, pattern, role in RULES:
        if rule_direction not in ("*", direction):
            continue
        if re.search(pattern, text):
            return role, True
    return DEFAULT_ROLE, False


def build_vocabulary(pairs: set[tuple[str, str]]) -> dict[str, dict[str, str]]:
    """pairs: (description, direction). Returns {description: {"role", "direction", "source"}}."""
    vocab: dict[str, dict[str, str]] = {}
    for description, direction in sorted(pairs):
        role, matched = classify(description, direction)
        entry = {"role": role, "direction": direction, "source": "rule" if matched else "default"}
        if description in vocab and vocab[description]["role"] != role:
            raise ValueError(f"description {description!r} gets conflicting roles by direction")
        vocab[description] = entry
    return vocab


def write_vocabulary(vocab: dict[str, dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": "keyword_rules_v1", "entries": vocab}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def load_vocabulary(path: Path) -> dict[str, str]:
    """{description: role}"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {desc: entry["role"] for desc, entry in payload["entries"].items()}
