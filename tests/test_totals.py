from decimal import Decimal

from checkout.checkout import compute_total
from tests.conftest import make_cart, make_order


def test_total_adds_gst_to_subtotal():
    totals = compute_total(make_order(make_cart("200", "300")))
    assert totals.subtotal == Decimal("500.00")
    assert totals.tax == Decimal("90.00")
    assert totals.total == Decimal("590.00")


def test_half_paisa_rounds_up():
    # 12.75 * 1.18 = 15.045 -> customer pays 15.05, never 15.04
    totals = compute_total(make_order(make_cart("12.75")))
    assert totals.total == Decimal("15.05")


def test_gst_is_charged_on_the_discounted_amount():
    totals = compute_total(make_order(make_cart("1000"), codes=("DIWALI10",)))
    assert totals.discount == Decimal("100.00")
    assert totals.tax == Decimal("162.00")
    assert totals.total == Decimal("1062.00")
