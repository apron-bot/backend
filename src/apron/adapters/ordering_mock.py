
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from uuid import uuid4

from apron.domain.enums import OrderStatus
from apron.domain.models import Order, OrderItem


class MockOrderingAdapter:
    """Fake Glovo/Mercadona/Carrefour responses for demo."""

    MOCK_PRICES = {
        "mercadona": {"chicken": 5.99, "rice": 1.20, "olive oil": 3.49, "milk": 1.10, "egg": 2.10},
        "carrefour": {"chicken": 6.49, "rice": 0.99, "olive oil": 3.99, "milk": 1.29, "egg": 2.35},
    }

    async def search_products(self, items: list[str], store: str) -> list[OrderItem]:
        catalog = self.MOCK_PRICES.get(store.lower(), self.MOCK_PRICES["mercadona"])
        results: list[OrderItem] = []
        for item in items:
            base = catalog.get(item.lower(), 2.0)
            variance = random.uniform(-0.15, 0.15)
            results.append(OrderItem(name=item, quantity=1, unit="units", price=round(base + variance, 2)))
        return results

    async def place_order(self, items, store, address) -> Order:
        _ = address
        await asyncio.sleep(2)
        return Order(
            id=uuid4(),
            user_id=uuid4(),
            items=items,
            source=store,
            status=OrderStatus.CONFIRMED,
            total_price=round(sum(i.price for i in items), 2),
            estimated_delivery_minutes=random.randint(30, 50),
            created_at=datetime.now(timezone.utc),
        )
