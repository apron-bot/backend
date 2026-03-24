
from __future__ import annotations

from uuid import uuid4

from apron.domain.enums import ConversationState, OrderStatus
from apron.domain.models import Order
from apron.ports.messaging import MessagingPort
from apron.ports.ordering import OrderingPort
from apron.ports.repositories import OrderRepository, ShoppingListRepository, UserRepository


class OrderingService:
    def __init__(
        self,
        ordering_port: OrderingPort,
        shopping_repo: ShoppingListRepository,
        order_repo: OrderRepository,
        messaging: MessagingPort,
        user_repo: UserRepository,
    ) -> None:
        self._ordering_port = ordering_port
        self._shopping_repo = shopping_repo
        self._order_repo = order_repo
        self._messaging = messaging
        self._user_repo = user_repo
        self._last_quote: dict[str, tuple[str, list]] = {}

    async def start_order(self, user) -> None:
        shopping = await self._shopping_repo.get_list(user.id)
        names = [item.name for item in shopping]
        mercadona = await self._ordering_port.search_products(names, "mercadona")
        carrefour = await self._ordering_port.search_products(names, "carrefour")
        m_total = sum(i.price for i in mercadona)
        c_total = sum(i.price for i in carrefour)
        self._last_quote[str(user.id)] = ("mercadona", mercadona)
        await self._user_repo.update(user.model_copy(update={"conversation_state": ConversationState.ORDERING_MODE}))
        await self._messaging.send_text(
            user.phone_number,
            f"Mercadona: EUR {m_total:.2f} | Carrefour: EUR {c_total:.2f}. Reply confirm/cancel/store name.",
        )

    async def handle(self, user, message: str) -> None:
        msg = message.strip().lower()
        if msg in {"cancel", "stop"}:
            await self._user_repo.update(user.model_copy(update={"conversation_state": ConversationState.IDLE}))
            await self._messaging.send_text(user.phone_number, "Order canceled.")
            return

        if msg in {"carrefour", "mercadona"}:
            shopping = await self._shopping_repo.get_list(user.id)
            quote = await self._ordering_port.search_products([item.name for item in shopping], msg)
            self._last_quote[str(user.id)] = (msg, quote)
            await self._messaging.send_text(
                user.phone_number, f"Updated {msg} quote: EUR {sum(i.price for i in quote):.2f}."
            )
            return

        if msg in {"confirm", "go ahead"}:
            store, items = self._last_quote.get(str(user.id), ("mercadona", []))
            order = await self._ordering_port.place_order(items, store, "Demo Address")
            persisted = await self._order_repo.save(
                Order(
                    id=uuid4(),
                    user_id=user.id,
                    items=order.items,
                    source=store,
                    status=OrderStatus.CONFIRMED,
                    total_price=sum(i.price for i in items),
                    estimated_delivery_minutes=order.estimated_delivery_minutes,
                    created_at=order.created_at,
                )
            )
            await self._user_repo.update(user.model_copy(update={"conversation_state": ConversationState.IDLE}))
            await self._messaging.send_text(
                user.phone_number, f"Order confirmed: {persisted.source} EUR {persisted.total_price:.2f}."
            )
            return

        await self._messaging.send_text(user.phone_number, "Reply confirm, cancel, or a store name.")

    async def order_delivery(self, user, message: str) -> None:
        _ = message
        await self._messaging.send_text(
            user.phone_number,
            "I found 3 delivery options. Reply ORDER to confirm your preferred one.",
        )
