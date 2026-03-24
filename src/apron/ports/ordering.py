from typing import Protocol

from apron.domain.models import Order, OrderItem


class OrderingPort(Protocol):
    async def search_products(self, items: list[str], store: str) -> list[OrderItem]: ...

    async def place_order(
        self, items: list[OrderItem], store: str, delivery_address: str
    ) -> Order: ...
