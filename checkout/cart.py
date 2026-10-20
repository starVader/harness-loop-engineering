from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


@dataclass(frozen=True)
class LineItem:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass
class Cart:
    items: List[LineItem] = field(default_factory=list)

    def add(self, item: LineItem) -> None:
        self.items.append(item)

    def subtotal(self) -> Decimal:
        return sum((item.unit_price * item.quantity for item in self.items), Decimal("0"))
