"""Event rows -> dated cash flows in home currency, split by how the forecast uses them (plan §4.2)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Optional

from . import vocabulary as roles
from .config import FORECAST_DAYS
from .contracts import Dataset, Event, Profile, Request

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Flow:
    date: date
    amount: float            # home currency, always positive
    raw_amount: float        # in `currency`
    currency: str
    direction: str           # credit | debit
    category: str
    description: str
    role: str
    source: str              # history | known | pending | projected | evidence
    event_id: Optional[str] = None
    flexibility: str = "fixed"
    minimum_allowed: Optional[float] = None
    series_key: Optional[tuple[str, ...]] = None

    @property
    def signed(self) -> float:
        return self.amount if self.direction == "credit" else -self.amount


@dataclass
class UserLedger:
    request: Request
    profile: Profile
    window_end: date
    history: list[Flow] = field(default_factory=list)   # settled before the request date
    known: list[Flow] = field(default_factory=list)     # scheduled / settled on or after the request date, in window
    pending: list[Flow] = field(default_factory=list)   # pending debits to reserve (disputed charges included)
    latest_debit_by_category: dict[str, Event] = field(default_factory=dict)


def resolve_amount(event: Event, image_amounts: dict[str, dict]) -> Optional[float]:
    if event.amount is not None:
        return event.amount
    extracted = image_amounts.get(event.event_id, {}).get("amount")
    return float(extracted) if extracted is not None else None


def build_ledger(ds: Dataset, request: Request, vocab: dict[str, str], image_amounts: dict[str, dict]) -> UserLedger:
    profile = ds.profiles[request.user_id]
    start = request.request_date
    ledger = UserLedger(request=request, profile=profile, window_end=start + timedelta(days=FORECAST_DAYS))
    events = ds.events_by_user.get(request.user_id, [])

    for e in events:
        if e.direction == "debit" and e.settlement_date < start and e.status == "settled":
            ledger.latest_debit_by_category[e.category] = e  # events are sorted by settlement date

    for e in events:
        if e.direction not in ("credit", "debit") or e.status in ("cancelled", "failed", "unrealized"):
            continue
        amount = resolve_amount(e, image_amounts)
        if amount is None:
            if e.status == "settled":
                log.info("skip settled %s with unreadable amount (history only)", e.event_id)
                continue
            raise ValueError(f"{e.event_id}: blank amount with no extracted image amount")
        home = ds.fx.convert(amount, e.currency, profile.home_currency, e.settlement_date)
        flow = Flow(
            date=e.settlement_date, amount=home, raw_amount=amount, currency=e.currency, direction=e.direction,
            category=e.category, description=e.description, role=vocab.get(e.description, roles.RECURRING),
            source="history", event_id=e.event_id, flexibility=e.flexibility,
            minimum_allowed=e.minimum_allowed_amount,
        )
        if e.status == "settled" and e.settlement_date < start:
            ledger.history.append(flow)
        elif e.status == "pending":
            if e.direction == "debit":
                ledger.pending.append(replace(flow, source="pending"))
            # pending credits are never counted
        elif start <= e.settlement_date <= ledger.window_end:  # scheduled, or settled on/after the request date
            ledger.known.append(replace(flow, source="known"))
    return ledger
