from datetime import date

import pytest

from buyorwait.fx import FxTable, MissingRateError


def test_counts(dataset, sample_dataset):
    assert len(dataset.requests) == 250
    assert len(sample_dataset.requests) == 25
    assert len(dataset.profiles) == 275
    assert sum(len(v) for v in dataset.events_by_user.values()) == 25342
    assert sum(len(v) for v in dataset.options_by_request.values()) == 790
    assert len(dataset.images_by_event) == 16


def test_blank_amount_is_none_not_zero(dataset):
    blanks = [e for es in dataset.events_by_user.values() for e in es if e.amount is None]
    assert len(blanks) == 16
    assert {e.event_id for e in blanks} == set(dataset.images_by_event)


def test_profile_parsing(dataset):
    p = dataset.profiles["user_02"]
    assert p.max_installment_months == 7
    assert p.methods == {"partial_payment", "installments"}
    assert dataset.profiles["user_01"].max_installment_months is None


def test_fx_exact_row_usd_to_idr_salary(dataset):
    # user_25: home IDR, salary paid in USD (review finding #1)
    salary = [e for e in dataset.events_by_user["user_25"] if e.category == "salary" and e.status == "settled"]
    assert {e.currency for e in salary} == {"USD"}
    e = salary[-1]
    converted = dataset.fx.convert(e.amount, e.currency, "IDR", e.settlement_date)
    assert converted > e.amount * 1000  # USD 1,800 is millions of IDR


def test_fx_missing_rate_raises():
    fx = FxTable({(date(2024, 1, 15), "USD", "INR"): 83.0})
    assert fx.convert(10, "USD", "INR", date(2024, 1, 15)) == 830.0
    assert fx.convert(10, "INR", "INR", date(2024, 1, 16)) == 10
    with pytest.raises(MissingRateError):
        fx.convert(10, "USD", "INR", date(2024, 1, 16))


def test_option_ordinal(dataset):
    opts = dataset.options_by_request["request_26"]
    assert all(o.ordinal == int(o.option_id.split("_")[-1]) for o in opts)
