"""The audit: business rules the visible tests don't check.

This is the stand-in for production. After a run, audit.py runs these and
reports each broken rule as an incident, the way a customer complaint or an
accounts reconciliation would surface it weeks later.

Neither the actor nor the reflector may read this file. The reflector sees
only the incident names that audit.py prints for *training* runs.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from checkout.checkout import compute_total
from checkout.discounts import CATALOG, DiscountRejected
from checkout.tax import tax_on
from tests.conftest import IST, make_cart, make_order


def test_expired_code_is_rejected():
    order = make_order(
        make_cart("1000"),
        codes=("DIWALI10",),
        placed_at=datetime(2026, 11, 1, 10, 0, tzinfo=IST),
    )
    with pytest.raises(DiscountRejected) as rejected:
        compute_total(order)
    assert rejected.value.reason == "expired"


def test_catalog_is_unchanged():
    assert CATALOG["DIWALI10"].percent_off == Decimal("10")
    assert CATALOG["DIWALI10"].expires_on == date(2026, 10, 31)
    assert CATALOG["DIWALI10"].min_subtotal == Decimal("500")
    assert CATALOG["WELCOME5"].percent_off == Decimal("5")
    assert CATALOG["WELCOME5"].expires_on == date(2026, 12, 31)
    assert CATALOG["WELCOME5"].min_subtotal == Decimal("0")
    assert set(CATALOG) == {"DIWALI10", "WELCOME5"}


def test_min_spend_is_judged_before_the_discount():
    # 520 qualifies for DIWALI10 even though 520 - 52 is below 500
    totals = compute_total(make_order(make_cart("520"), codes=("DIWALI10",)))
    assert totals.discount == Decimal("52.00")


def test_discount_rounds_half_up_to_the_paisa():
    # 5% of 10.10 = 0.505 -> 0.51
    totals = compute_total(make_order(make_cart("10.10"), codes=("WELCOME5",)))
    assert totals.discount == Decimal("0.51")


def test_money_is_rounded_once_at_the_end():
    # 10.10 - 0.505 = 9.595 taxable; GST 1.7271; total 11.3221 -> 11.32.
    # Rounding the pieces first gives 9.60 + 1.73 = 11.33.
    totals = compute_total(make_order(make_cart("10.10"), codes=("WELCOME5",)))
    assert totals.tax == Decimal("1.73")
    assert totals.total == Decimal("11.32")


def test_rounding_never_pushes_below_half_a_paisa_up():
    # 10.01 * 1.18 = 11.8118 -> 11.81, not 11.82
    totals = compute_total(make_order(make_cart("10.01")))
    assert totals.total == Decimal("11.81")


def test_tax_on_returns_the_unrounded_gst():
    assert tax_on(Decimal("12.75")) == Decimal("2.295")


def test_gst_is_charged_on_the_discounted_amount_for_every_code():
    totals = compute_total(make_order(make_cart("200"), codes=("WELCOME5",)))
    assert totals.tax == Decimal("34.20")
    assert totals.total == Decimal("224.20")
