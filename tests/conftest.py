
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest

from apron.domain.enums import (
    ConversationState,
    CookingSkill,
    IngredientSource,
    MealType,
    OrderStatus,
    TimeAvailability,
)
from apron.domain.models import (
    InventoryItem,
    MealPlan,
    Order,
    OrderItem,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    ShoppingListItem,
    UserProfile,
)


class FakeUserRepository:
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


class FakeInventoryRepository:
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
        for user_items in self._items.values():
            user_items.pop(item_id, None)


class FakeMealPlanRepository:
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


class FakeRecipeRepository:
    def __init__(self):
        self._favorites: dict[UUID, list[Recipe]] = {}

    async def get_favorites(self, user_id: UUID) -> list[Recipe]:
        return self._favorites.get(user_id, [])

    async def save_favorite(self, user_id: UUID, recipe: Recipe) -> None:
        self._favorites.setdefault(user_id, []).append(recipe)

    async def search(self, query: str, filters: dict) -> list[Recipe]:
        return []


class FakeOrderRepository:
    def __init__(self):
        self._orders: dict[UUID, list[Order]] = {}

    async def save(self, order: Order) -> Order:
        self._orders.setdefault(order.user_id, []).append(order)
        return order

    async def get_history(self, user_id: UUID, limit: int = 20) -> list[Order]:
        return self._orders.get(user_id, [])[-limit:]


class FakeShoppingListRepository:
    def __init__(self):
        self._items: dict[UUID, list[ShoppingListItem]] = {}

    async def get_list(self, user_id: UUID) -> list[ShoppingListItem]:
        return list(self._items.get(user_id, []))

    async def add_items(self, items: list[ShoppingListItem]) -> None:
        for item in items:
            self._items.setdefault(item.user_id, []).append(item)

    async def mark_purchased(self, item_ids: list[UUID]) -> None:
        for uid, items in self._items.items():
            self._items[uid] = [
                item if item.id not in set(item_ids) else item.model_copy(update={"purchased": True})
                for item in items
            ]

    async def clear(self, user_id: UUID) -> None:
        self._items[user_id] = []


class FakeMessaging:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, to: str, body: str) -> None:
        self.sent.append({"type": "text", "to": to, "body": body})

    async def send_image(self, to: str, image_url: str, caption: str) -> None:
        self.sent.append({"type": "image", "to": to, "image_url": image_url, "caption": caption})

    async def send_template(self, to: str, template: str, params: dict) -> None:
        self.sent.append({"type": "template", "to": to, "template": template, "params": params})


class FakeLLM:
    def __init__(self, responses: dict[str, str] | None = None):
        self._responses = responses or {}
        self.calls: list[dict] = []

    async def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> str:
        self.calls.append({"type": "chat", "system": system, "messages": messages, "tools": tools})
        for key, response in self._responses.items():
            if key in system or any(key in str(m) for m in messages):
                return response
        return '{"intent": "unknown", "entities": {}}'

    async def vision(self, system: str, image_b64: str, prompt: str) -> str:
        self.calls.append({"type": "vision", "system": system, "prompt": prompt, "image": image_b64})
        for key, response in self._responses.items():
            if key in system or key in prompt:
                return response
        return json.dumps(
            [
                {"name": "milk", "quantity": 1000, "unit": "ml", "estimated_expiry": "2025-07-20"},
                {"name": "egg", "quantity": 6, "unit": "units", "estimated_expiry": "2025-07-25"},
            ]
        )

    async def generate_image(self, prompt: str, style: str = "pixel_art") -> str:
        self.calls.append({"type": "image", "prompt": prompt, "style": style})
        return "https://example.com/image.png"


class FakeOrderingPort:
    async def search_products(self, items: list[str], store: str) -> list[OrderItem]:
        return [OrderItem(name=i, quantity=1, unit="units", price=1.99) for i in items]

    async def place_order(self, items: list[OrderItem], store: str, delivery_address: str) -> Order:
        return Order(
            id=uuid4(),
            user_id=uuid4(),
            items=items,
            source=store,
            status=OrderStatus.CONFIRMED,
            total_price=sum(i.price for i in items),
            estimated_delivery_minutes=35,
            created_at=datetime.now(timezone.utc),
        )


class FakeClock:
    def __init__(self, frozen: datetime = datetime(2025, 7, 14, 9, 0, tzinfo=timezone.utc)):
        self._frozen = frozen

    def now(self) -> datetime:
        return self._frozen

    def today(self) -> date:
        return self._frozen.date()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sample_user(fake_clock: FakeClock) -> UserProfile:
    now = fake_clock.now()
    return UserProfile(
        id=uuid4(),
        phone_number="+34612345678",
        household_size=2,
        allergies=[],
        dietary_preferences=[],
        taste_profiles=[],
        weekly_budget=100.0,
        preferred_cuisines=["mediterranean"],
        cooking_skill=CookingSkill.INTERMEDIATE,
        time_available=TimeAvailability.NORMAL,
        disliked_ingredients=[],
        conversation_state=ConversationState.IDLE,
        onboarding_step=0,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def sample_recipe() -> Recipe:
    return Recipe(
        id=uuid4(),
        name="Chicken Rice",
        description="Simple bowl",
        cuisine="mediterranean",
        cook_time_minutes=30,
        difficulty=CookingSkill.INTERMEDIATE,
        servings=2,
        ingredients=[
            RecipeIngredient(name="chicken", quantity=300, unit="g"),
            RecipeIngredient(name="rice", quantity=200, unit="g"),
        ],
        steps=["Cook rice", "Cook chicken"],
        image_url=None,
        tags=[],
    )


@pytest.fixture
def sample_inventory(sample_user: UserProfile, fake_clock: FakeClock) -> list[InventoryItem]:
    return [
        InventoryItem(
            id=uuid4(),
            user_id=sample_user.id,
            name="chicken",
            quantity=500,
            unit="g",
            expiry_date=date(2025, 7, 15),
            date_added=fake_clock.now(),
            source=IngredientSource.MANUAL,
        ),
        InventoryItem(
            id=uuid4(),
            user_id=sample_user.id,
            name="rice",
            quantity=400,
            unit="g",
            expiry_date=None,
            date_added=fake_clock.now(),
            source=IngredientSource.MANUAL,
        ),
    ]
