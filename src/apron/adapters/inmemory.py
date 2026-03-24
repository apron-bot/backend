from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID

from apron.domain.enums import OrderStatus
from apron.domain.models import InventoryItem, MealPlan, Order, OrderItem, Recipe, ShoppingListItem, UserProfile


class InMemoryUserRepository:
    def __init__(self):
        self._users: dict[UUID, UserProfile] = {}
        self._by_phone: dict[str, UUID] = {}

    async def get_by_phone(self, phone: str) -> UserProfile | None:
        uid = self._by_phone.get(phone)
        return self._users.get(uid) if uid else None

    async def get_by_id(self, user_id: UUID) -> UserProfile:
        return self._users[user_id]

    async def save(self, user: UserProfile) -> UserProfile:
        self._users[user.id] = user
        self._by_phone[user.phone_number] = user.id
        return user

    async def update(self, user: UserProfile) -> UserProfile:
        self._users[user.id] = user
        self._by_phone[user.phone_number] = user.id
        return user


class InMemoryInventoryRepository:
    def __init__(self):
        self._items: dict[UUID, dict[UUID, InventoryItem]] = {}

    async def get_all(self, user_id: UUID) -> list[InventoryItem]:
        return list(self._items.get(user_id, {}).values())

    async def upsert(self, item: InventoryItem) -> InventoryItem:
        self._items.setdefault(item.user_id, {})[item.id] = item
        return item

    async def bulk_upsert(self, items: list[InventoryItem]) -> list[InventoryItem]:
        for item in items:
            await self.upsert(item)
        return items

    async def delete(self, item_id: UUID) -> None:
        for items in self._items.values():
            items.pop(item_id, None)


class InMemoryMealPlanRepository:
    def __init__(self):
        self._plans: dict[UUID, MealPlan] = {}

    async def get_current(self, user_id: UUID) -> MealPlan | None:
        return self._plans.get(user_id)

    async def save(self, plan: MealPlan) -> MealPlan:
        self._plans[plan.user_id] = plan
        return plan

    async def update(self, plan: MealPlan) -> MealPlan:
        self._plans[plan.user_id] = plan
        return plan


class InMemoryRecipeRepository:
    def __init__(self):
        self._favorites: dict[UUID, list[Recipe]] = {}

    async def get_favorites(self, user_id: UUID) -> list[Recipe]:
        return self._favorites.get(user_id, [])

    async def save_favorite(self, user_id: UUID, recipe: Recipe) -> None:
        self._favorites.setdefault(user_id, []).append(recipe)

    async def search(self, query: str, filters: dict) -> list[Recipe]:
        _ = query
        _ = filters
        return []


class InMemoryOrderRepository:
    def __init__(self):
        self._orders: dict[UUID, list[Order]] = {}

    async def save(self, order: Order) -> Order:
        self._orders.setdefault(order.user_id, []).append(order)
        return order

    async def get_history(self, user_id: UUID, limit: int = 20) -> list[Order]:
        return self._orders.get(user_id, [])[-limit:]


class InMemoryShoppingListRepository:
    def __init__(self):
        self._items: dict[UUID, list[ShoppingListItem]] = {}

    async def get_list(self, user_id: UUID) -> list[ShoppingListItem]:
        return list(self._items.get(user_id, []))

    async def add_items(self, items: list[ShoppingListItem]) -> None:
        for item in items:
            self._items.setdefault(item.user_id, []).append(item)

    async def mark_purchased(self, item_ids: list[UUID]) -> None:
        ids = set(item_ids)
        for uid, items in self._items.items():
            self._items[uid] = [
                i if i.id not in ids else i.model_copy(update={"purchased": True}) for i in items
            ]

    async def clear(self, user_id: UUID) -> None:
        self._items[user_id] = []


class InMemoryMessaging:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, to: str, body: str) -> None:
        self.sent.append({"type": "text", "to": to, "body": body})

    async def send_image(self, to: str, image_url: str, caption: str) -> None:
        self.sent.append({"type": "image", "to": to, "image_url": image_url, "caption": caption})

    async def send_template(self, to: str, template: str, params: dict) -> None:
        self.sent.append({"type": "template", "to": to, "template": template, "params": params})


class InMemoryLLM:
    async def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> str:
        _ = tools
        if "Classify intent" in system:
            return json.dumps({"intent": "unknown", "entities": {}})
        if "Generate three recipes" in system:
            return json.dumps({"recipes": []})
        return "OK"

    async def vision(self, system: str, image_b64: str, prompt: str) -> str:
        _ = system
        _ = image_b64
        _ = prompt
        return json.dumps([{"name": "milk", "quantity": 1000, "unit": "ml", "estimated_expiry": "2025-07-20"}])

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        _ = prompt
        _ = style
        return "https://example.com/fake-image.png"


class InMemoryOrdering:
    async def search_products(self, items: list[str], store: str) -> list[OrderItem]:
        _ = store
        return [OrderItem(name=i, quantity=1, unit="units", price=1.99) for i in items]

    async def place_order(self, items: list[OrderItem], store: str, delivery_address: str) -> Order:
        _ = delivery_address
        return Order(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            items=items,
            source=store,
            status=OrderStatus.CONFIRMED,
            total_price=sum(i.price for i in items),
            estimated_delivery_minutes=35,
            created_at=datetime.now(timezone.utc),
        )


class InMemoryClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        return date.today()
