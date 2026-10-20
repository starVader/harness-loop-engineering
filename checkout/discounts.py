from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict


@dataclass(frozen=True)
class DiscountCode:
    code: str
    percent_off: Decimal
    expires_on: date  # last valid day, inclusive
    min_subtotal: Decimal


class DiscountRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


CATALOG: Dict[str, DiscountCode] = {
    "DIWALI10": DiscountCode("DIWALI10", Decimal("10"), date(2026, 10, 31), Decimal("500")),
    "WELCOME5": DiscountCode("WELCOME5", Decimal("5"), date(2026, 12, 31), Decimal("0")),
}


def validate_code(
    raw_code: str,
    subtotal: Decimal,
    order_date: date,
    catalog: Dict[str, DiscountCode],
) -> DiscountCode:
    """Return the discount if `raw_code` may be used on this order, else raise DiscountRejected."""
    code = catalog.get(raw_code.strip().upper())
    if code is None:
        raise DiscountRejected("unknown")
    if order_date > code.expires_on:
        raise DiscountRejected("expired")
    if subtotal <= code.min_subtotal:
        raise DiscountRejected("below_min_spend")
    return code


def discount_amount(subtotal: Decimal, code: DiscountCode) -> Decimal:
    return subtotal * code.percent_off / Decimal("100")
