from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional, Tuple

from checkout.cart import Cart
from checkout.discounts import CATALOG, DiscountCode, DiscountRejected, discount_amount, validate_code
from checkout.tax import tax_on

PAISE = Decimal("0.01")


@dataclass(frozen=True)
class Order:
    cart: Cart
    placed_at: datetime
    paid_at: Optional[datetime] = None  # cash-on-delivery orders settle after delivery
    codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal


def round_money(amount: Decimal) -> Decimal:
    return amount.quantize(PAISE, rounding=ROUND_HALF_UP)


def _order_date(order: Order) -> date:
    return order.placed_at.date()


def compute_total(order: Order, catalog: Dict[str, DiscountCode] = CATALOG) -> Totals:
    if len(order.codes) > 1:
        raise DiscountRejected("one_code_per_order")

    subtotal = order.cart.subtotal()
    discount = Decimal("0")
    if order.codes:
        code = validate_code(order.codes[0], subtotal, _order_date(order), catalog)
        discount = discount_amount(subtotal, code)

    taxable = subtotal - discount
    tax = tax_on(taxable)
    return Totals(
        subtotal=round_money(subtotal),
        discount=round_money(discount),
        tax=round_money(tax),
        total=round_money(taxable + tax),
    )
