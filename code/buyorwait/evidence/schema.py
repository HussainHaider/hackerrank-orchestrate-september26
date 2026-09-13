"""Closed evidence vocabulary returned by the extractors (plan §3.3). The engine reads only these fields."""
from __future__ import annotations

from .. import vocabulary as vocab

EFFECT_TYPES = [
    "series_amount_change",   # amount or percent applies to a series from `date` (or next occurrence)
    "one_time_amount_change", # one occurrence changes amount
    "temporary_amount",       # amount applies until `until`
    "series_starts",          # a new stream starts on `date`
    "series_ends",            # a stream stops from `date`
    "occurrence_moved",       # an occurrence moves to `date`
    "confirmed_credit",       # a specific credit is confirmed for `date`
    "not_confirmed",          # bonus/commission/prize/refund/payout not yet received: never counted
    "already_settled",        # proceeds already received: never project again
    "failed_debit_retry",     # a failed debit will be retried; obligation still open
    "internal_transfer",      # own-account transfer; no engine action
    "non_cash",               # valuation change only
    "disputed_charge",        # charge under investigation, no reversal posted
    "receipt_pointer",        # amount is on a receipt/image
    "solicitation",           # asks the user to pay/act to receive money: untrusted, no effect
    "no_effect",
]

_nullable_str = {"type": ["string", "null"]}
_nullable_num = {"type": ["number", "null"]}

MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": EFFECT_TYPES},
                    "target_kind": {"type": "string", "enum": ["event", "series", "none"]},
                    "event_id": _nullable_str,
                    "category": _nullable_str,
                    "direction": {"type": ["string", "null"], "enum": ["credit", "debit", None]},
                    "amount": _nullable_num,
                    "percent": _nullable_num,
                    "currency": _nullable_str,
                    "date": _nullable_str,
                    "until": _nullable_str,
                    "quote": {"type": "string"},
                },
                "required": ["type", "target_kind", "event_id", "category", "direction", "amount", "percent", "currency", "date", "until", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["effects"],
    "additionalProperties": False,
}

IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "amount": _nullable_num,
        "currency": _nullable_str,
        "field_used": {"type": "string"},
        "document_type": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["amount", "currency", "field_used", "document_type", "confidence"],
    "additionalProperties": False,
}

VOCAB_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"description": {"type": "string"}, "role": {"type": "string", "enum": sorted(vocab.ROLES)}},
                "required": ["description", "role"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}
