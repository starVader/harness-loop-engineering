from decimal import Decimal

from checkout.tax import tax_on


def test_gst_is_eighteen_percent():
    assert tax_on(Decimal("100")) == Decimal("18.00")
