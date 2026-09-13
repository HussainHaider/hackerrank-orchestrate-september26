from buyorwait import vocabulary as v


def _pairs(dataset):
    return {(e.description, e.direction) for es in dataset.events_by_user.values() for e in es}


def test_every_description_gets_a_single_role(dataset):
    vocab = v.build_vocabulary(_pairs(dataset))
    assert len(vocab) == 164
    assert all(entry["role"] in v.ROLES for entry in vocab.values())


def test_income_lifecycle_roles():
    assert v.classify("Final employer payroll", "credit")[0] == v.INCOME_ENDS
    assert v.classify("Previous employer payroll", "credit")[0] == v.INCOME_ENDED_STREAM
    assert v.classify("First-job payroll", "credit")[0] == v.INCOME_STARTS
    assert v.classify("Payroll before leave", "credit")[0] == v.INCOME_PAUSE
    assert v.classify("Payroll after returning from leave", "credit")[0] == v.INCOME_RESUME
    assert v.classify("Quarterly performance bonus", "credit")[0] == v.UNCONFIRMED_INCOME
    assert v.classify("Monthly sales commission", "credit")[0] == v.UNCONFIRMED_INCOME
    assert v.classify("Delivery platform payout", "credit")[0] == v.VARIABLE_INCOME
    assert v.classify("Consulting invoice payment", "credit")[0] == v.VARIABLE_INCOME
    assert v.classify("Payroll credit", "credit")[0] == v.RECURRING
    assert v.classify("Next confirmed salary", "credit")[0] == v.KNOWN_FUTURE


def test_charge_roles():
    assert v.classify("Possible duplicate card charge", "debit")[0] == v.DISPUTED_CHARGE
    assert v.classify("Pending fuel authorization", "debit")[0] == v.PENDING_CHARGE
    assert v.classify("Scheduled bill payment retry", "debit")[0] == v.KNOWN_EXTRA
    assert v.classify("Outstanding rent balance", "debit")[0] == v.KNOWN_EXTRA
    assert v.classify("Scheduled insurance payment", "debit")[0] == v.KNOWN_FUTURE
    assert v.classify("Grocery tax invoice", "debit")[0] == v.ONE_OFF
    assert v.classify("Current portfolio valuation", "non_cash")[0] == v.NON_CASH


def test_defaulted_strings_are_only_routine_flows(dataset):
    """Anything not matched by a rule must be a routine category flow seen many times."""
    counts = {}
    for es in dataset.events_by_user.values():
        for e in es:
            counts[e.description] = counts.get(e.description, 0) + 1
    vocab = v.build_vocabulary(_pairs(dataset))
    defaulted = [d for d, entry in vocab.items() if entry["source"] == "default"]
    assert defaulted, "expected routine expense strings to fall through"
    assert all(counts[d] >= 20 for d in defaulted), [d for d in defaulted if counts[d] < 20]
