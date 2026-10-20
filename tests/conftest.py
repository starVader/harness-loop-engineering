from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple

from checkout.cart import Cart, LineItem
from checkout.checkout import Order

IST = timezone(timedelta(hours=5, minutes=30))


def make_cart(*prices: str) -> Cart:
    cart = Cart()
    for index, price in enumerate(prices):
        cart.add(LineItem(sku=f"SKU-{index}", unit_price=Decimal(price), quantity=1))
    return cart


def make_order(
    cart: Cart,
    codes: Tuple[str, ...] = (),
    placed_at: datetime = datetime(2026, 10, 30, 11, 0, tzinfo=IST),
    paid_at: Optional[datetime] = None,
) -> Order:
    # Prepaid by default: payment captured the moment the order is placed.
    return Order(cart=cart, placed_at=placed_at, paid_at=paid_at or placed_at, codes=codes)
