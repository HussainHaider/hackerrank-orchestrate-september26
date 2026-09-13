"""CSV -> contracts. The only module that reads dataset files."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from .contracts import Dataset, Event, ImageRef, Message, PaymentOption, Profile, Request
from .fx import FxTable


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _opt_float(value: str) -> Optional[float]:
    value = value.strip()
    return float(value) if value else None


def _opt_str(value: str) -> Optional[str]:
    value = value.strip()
    return value or None


def _split(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.strip().split("|") if part)


def load_profiles(path: Path) -> dict[str, Profile]:
    out = {}
    for r in _rows(path):
        months = r["max_installment_months"].strip()
        out[r["user_id"]] = Profile(
            user_id=r["user_id"],
            home_currency=r["home_currency"],
            balance=float(r["current_available_balance"]),
            minimum_balance=float(r["minimum_balance_to_keep"]),
            priorities=_split(r["financial_priorities"]),
            protected=frozenset(_split(r["expense_categories_to_protect"])),
            reducible_categories=frozenset(_split(r["expense_categories_user_is_willing_to_reduce"])),
            stoppable_categories=frozenset(_split(r["expense_categories_user_is_willing_to_stop"])),
            methods=frozenset(_split(r["payment_methods_user_will_consider"])),
            max_installment_months=int(months) if months else None,
        )
    return out


def load_events(path: Path) -> list[Event]:
    return [
        Event(
            event_id=r["event_id"],
            user_id=r["user_id"],
            event_type=r["event_type"],
            description=r["description"],
            category=r["category"],
            direction=r["direction"],
            amount=_opt_float(r["amount"]),
            currency=r["currency"],
            event_date=date.fromisoformat(r["event_date"]),
            settlement_date=date.fromisoformat(r["settlement_date"] or r["event_date"]),
            status=r["status"],
            linked_event_id=_opt_str(r["linked_event_id"]),
            flexibility=r["flexibility"],
            minimum_allowed_amount=_opt_float(r["minimum_allowed_amount"]),
        )
        for r in _rows(path)
    ]


def load_requests(path: Path) -> list[Request]:
    return [
        Request(
            request_id=r["request_id"],
            user_id=r["user_id"],
            request_date=date.fromisoformat(r["request_date"]),
            request_type=r["request_type"],
            requested_amount=float(r["requested_amount"]),
            deadline=date.fromisoformat(r["desired_completion_date"]),
            allows_partial_payment=r["allows_partial_payment"].strip().lower() == "true",
        )
        for r in _rows(path)
    ]


def load_options(path: Path) -> dict[str, list[PaymentOption]]:
    out: dict[str, list[PaymentOption]] = defaultdict(list)
    for r in _rows(path):
        freq = r["payment_frequency_days"].strip()
        out[r["request_id"]].append(
            PaymentOption(
                option_id=r["payment_option_id"],
                request_id=r["request_id"],
                method=r["payment_method"],
                payment_amount=float(r["payment_amount"]),
                number_of_payments=int(r["number_of_payments"]),
                first_payment_date=date.fromisoformat(r["first_payment_date"]),
                frequency_days=int(freq) if freq else None,
                financing_fee=float(r["financing_fee"] or 0),
                total_payable=float(r["total_payable_amount"]),
            )
        )
    return dict(out)


def load_fx(path: Path) -> FxTable:
    return FxTable(
        {(date.fromisoformat(r["rate_date"]), r["from_currency"], r["to_currency"]): float(r["rate"]) for r in _rows(path)}
    )


def load_messages(path: Path) -> dict[str, list[Message]]:
    out: dict[str, list[Message]] = defaultdict(list)
    for r in _rows(path):
        out[r["user_id"]].append(
            Message(
                message_id=r["message_id"],
                user_id=r["user_id"],
                request_id=_opt_str(r["request_id"]),
                related_event_id=_opt_str(r["related_event_id"]),
                sent_at=r["sent_at"],
                source_type=r["source_type"],
                text=r["message_text"],
            )
        )
    return dict(out)


def load_images(path: Path, media_dir: Path) -> dict[str, ImageRef]:
    return {
        r["related_event_id"]: ImageRef(
            image_id=r["image_id"],
            user_id=r["user_id"],
            request_id=_opt_str(r["request_id"]),
            related_event_id=r["related_event_id"],
            path=str(media_dir / f"{r['image_id']}.png"),
        )
        for r in _rows(path)
    }


def load_dataset(dataset_dir: Path, requests_file: Optional[Path] = None) -> Dataset:
    events = load_events(dataset_dir / "financial_events.csv")
    by_user: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        by_user[e.user_id].append(e)
    for es in by_user.values():
        es.sort(key=lambda e: (e.settlement_date, e.event_id))
    return Dataset(
        profiles=load_profiles(dataset_dir / "financial_profiles.csv"),
        events_by_user=dict(by_user),
        requests=load_requests(requests_file or dataset_dir / "requests.csv"),
        options_by_request=load_options(dataset_dir / "request_payment_options.csv"),
        messages_by_user=load_messages(dataset_dir / "messages.csv"),
        images_by_event=load_images(dataset_dir / "images.csv", dataset_dir / "media" / "images"),
        fx=load_fx(dataset_dir / "exchange_rates.csv"),
        events_by_id={e.event_id: e for e in events},
    )
