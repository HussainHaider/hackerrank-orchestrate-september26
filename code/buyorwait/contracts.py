"""Typed records shared by every module. Parsing happens in loaders; nothing here does I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Profile:
    user_id: str
    home_currency: str
    balance: float
    minimum_balance: float
    priorities: tuple[str, ...]
    protected: frozenset[str]
    reducible_categories: frozenset[str]
    stoppable_categories: frozenset[str]
    methods: frozenset[str]
    max_installment_months: Optional[int]  # None: user will not consider installments


@dataclass(frozen=True)
class Event:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str  # credit | debit | non_cash
    amount: Optional[float]  # None when blank; resolved from an image
    currency: str
    event_date: date
    settlement_date: date
    status: str  # settled | pending | scheduled | cancelled | failed | unrealized
    linked_event_id: Optional[str]
    flexibility: str  # fixed | reducible | stoppable | reducible_or_stoppable
    minimum_allowed_amount: Optional[float]


@dataclass(frozen=True)
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    deadline: date
    allows_partial_payment: bool


@dataclass(frozen=True)
class PaymentOption:
    option_id: str
    request_id: str
    method: str  # full_payment | installments
    payment_amount: float
    number_of_payments: int
    first_payment_date: date
    frequency_days: Optional[int]
    financing_fee: float
    total_payable: float

    @property
    def ordinal(self) -> int:
        """Numeric suffix, for the lowest-payment_option_id tie-breaker."""
        return int(self.option_id.rsplit("_", 1)[1])


@dataclass(frozen=True)
class Message:
    message_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]
    sent_at: str
    source_type: str
    text: str


@dataclass(frozen=True)
class ImageRef:
    image_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: str
    path: str


@dataclass
class Dataset:
    profiles: dict[str, Profile]
    events_by_user: dict[str, list[Event]]
    requests: list[Request]
    options_by_request: dict[str, list[PaymentOption]]
    messages_by_user: dict[str, list[Message]]
    images_by_event: dict[str, ImageRef]
    fx: "FxTable"  # noqa: F821 - defined in fx.py
    events_by_id: dict[str, Event] = field(default_factory=dict)
