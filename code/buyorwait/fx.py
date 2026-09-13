"""Dated currency conversion. An exact (date, from, to) row is required; a miss is an error."""
from __future__ import annotations

from datetime import date


class MissingRateError(LookupError):
    pass


class FxTable:
    def __init__(self, rates: dict[tuple[date, str, str], float]):
        self._rates = rates

    def convert(self, amount: float, from_currency: str, to_currency: str, on: date) -> float:
        if from_currency == to_currency:
            return amount
        try:
            return amount * self._rates[(on, from_currency, to_currency)]
        except KeyError:
            raise MissingRateError(f"no {from_currency}->{to_currency} rate for {on.isoformat()}") from None

    def has_rate(self, from_currency: str, to_currency: str, on: date) -> bool:
        return from_currency == to_currency or (on, from_currency, to_currency) in self._rates
