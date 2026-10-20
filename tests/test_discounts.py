from datetime import datetime
from decimal import Decimal

import pytest

from checkout.checkout import compute_total
from checkout.discounts import DiscountRejected
from tests.conftest import IST, make_cart, make_order


def test_unknown_code_is_rejected():
    with pytest.raises(DiscountRejected) as rejected:
        compute_total(make_order(make_cart("1000"), codes=("FREEMONEY",)))
    assert rejected.value.reason == "unknown"


def test_code_is_case_and_whitespace_insensitive():
    totals = compute_total(make_order(make_cart("1000"), codes=("  diwali10 ",)))
    assert totals.discount == Decimal("100.00")


def test_percent_discount_is_applied():
    totals = compute_total(make_order(make_cart("200"), codes=("WELCOME5",)))
    assert totals.discount == Decimal("10.00")


def test_below_min_spend_is_rejected():
    with pytest.raises(DiscountRejected) as rejected:
        compute_total(make_order(make_cart("499.99"), codes=("DIWALI10",)))
    assert rejected.value.reason == "below_min_spend"


def test_cart_exactly_at_min_spend_qualifies():
    totals = compute_total(make_order(make_cart("500"), codes=("DIWALI10",)))
    assert totals.discount == Decimal("50.00")


def test_only_one_code_per_order():
    with pytest.raises(DiscountRejected) as rejected:
        compute_total(make_order(make_cart("1000"), codes=("DIWALI10", "WELCOME5")))
    assert rejected.value.reason == "one_code_per_order"


def test_code_works_on_its_last_valid_day():
    order = make_order(
        make_cart("1000"),
        codes=("DIWALI10",),
        placed_at=datetime(2026, 10, 31, 23, 0, tzinfo=IST),
    )
    assert compute_total(order).discount == Decimal("100.00")


def test_discount_applies_to_cash_on_delivery_order():
    order = make_order(
        make_cart("1000"),
        codes=("DIWALI10",),
        placed_at=datetime(2026, 10, 30, 11, 0, tzinfo=IST),
        paid_at=datetime(2026, 11, 2, 16, 0, tzinfo=IST),
    )
    assert compute_total(order).discount == Decimal("100.00")
