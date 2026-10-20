from decimal import Decimal

from checkout.cart import Cart, LineItem


def test_subtotal_multiplies_price_by_quantity():
    cart = Cart()
    cart.add(LineItem(sku="TEA", unit_price=Decimal("249.50"), quantity=2))
    cart.add(LineItem(sku="MUG", unit_price=Decimal("399"), quantity=1))
    assert cart.subtotal() == Decimal("898.00")


def test_empty_cart_subtotal_is_zero():
    assert Cart().subtotal() == Decimal("0")
