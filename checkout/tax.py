from decimal import Decimal

GST_RATE = Decimal("0.18")


def tax_on(amount: Decimal) -> Decimal:
    """GST on an amount. Unrounded; checkout rounds once at the end."""
    return amount * GST_RATE
