"""Output number/date formats observed in the labelled samples (plan §5.5)."""
from __future__ import annotations

import math
from datetime import date


def floor_cents(value: float) -> float:
    return math.floor(value * 100 + 1e-6) / 100


def raw_amount(value: float) -> str:
    """amount_safe_to_pay: 603.3, 17229139.2, 25256"""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def plan_amount(value: float) -> str:
    """payment_plan / reduce_to: 620.40, 23.50, 665950"""
    value = round(value, 2)
    return f"{value:.0f}" if abs(value - round(value)) < 1e-9 else f"{value:.2f}"


def money(currency: str, value: float) -> str:
    """Explanations: ZAR 25,256 / EUR 620.40 / IDR 15,952,906.67"""
    value = round(value, 2)
    body = f"{value:,.0f}" if abs(value - round(value)) < 1e-9 else f"{value:,.2f}"
    return f"{currency} {body}"


def long_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B')} {d.year}"
