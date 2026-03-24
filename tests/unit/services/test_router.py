
from __future__ import annotations

import json

from apron.domain.enums import ConversationState
from apron.services.cooking import CookingSessionService
from apron.services.inventory import InventoryService
from apron.services.meal_planner import MealPlannerService
from apron.services.onboarding import OnboardingService
from apron.services.ordering import OrderingService
from apron.services.router import MessageRouterService


def build_router(fake_clock, llm_payload: str):
    from tests.conftest import (
        FakeInventoryRepository,
        FakeLLM,
        FakeMealPlanRepository,
        FakeMessaging,
        FakeOrderRepository,
        FakeOrderingPort,
        FakeRecipeRepository,
        FakeShoppingListRepository,
        FakeUserRepository,
    )

    user_repo = FakeUserRepository()
    messaging = FakeMessaging()
    llm = FakeLLM({"Classify intent": llm_payload})
    inventory_repo = FakeInventoryRepository()
    inventory = InventoryService(inventory_repo, llm, messaging)
    onboarding = OnboardingService(user_repo, inventory, messaging, fake_clock)
    planner = MealPlannerService(
        user_repo,
        inventory_repo,
        FakeMealPlanRepository(),
        FakeRecipeRepository(),
        llm,
        messaging,
        fake_clock,
    )
    ordering = OrderingService(
        FakeOrderingPort(),
        FakeShoppingListRepository(),
        FakeOrderRepository(),
        messaging,
        user_repo,
    )
    cooking = CookingSessionService(messaging, llm, inventory_repo, user_repo)
    router = MessageRouterService(user_repo, llm, messaging, onboarding, inventory, planner, cooking, ordering)
    return router, user_repo, messaging


async def test_unknown_phone_starts_onboarding(fake_clock):
    router, _, messaging = build_router(fake_clock, '{"intent":"unknown","entities":{}}')
    await router.handle("+34611112222", "hello")
    assert messaging.sent
    assert "Welcome to Apron" in messaging.sent[0]["body"]


async def test_idle_user_add_inventory_intent(fake_clock, sample_user):
    payload = json.dumps({"intent": "add_inventory", "entities": {}})
    router, user_repo, messaging = build_router(fake_clock, payload)
    await user_repo.save(sample_user.model_copy(update={"conversation_state": ConversationState.IDLE}))
    await router.handle(sample_user.phone_number, "add eggs")
    assert any("Added" in msg.get("body", "") for msg in messaging.sent)


async def test_cooking_mode_dispatches(fake_clock, sample_user):
    router, user_repo, messaging = build_router(fake_clock, '{"intent":"unknown","entities":{}}')
    await user_repo.save(sample_user.model_copy(update={"conversation_state": ConversationState.COOKING_MODE}))
    await router.handle(sample_user.phone_number, "next")
    assert messaging.sent[-1]["body"] in {"No active cooking session."}


async def test_ordering_mode_dispatches(fake_clock, sample_user):
    router, user_repo, messaging = build_router(fake_clock, '{"intent":"unknown","entities":{}}')
    await user_repo.save(sample_user.model_copy(update={"conversation_state": ConversationState.ORDERING_MODE}))
    await router.handle(sample_user.phone_number, "cancel")
    assert "canceled" in messaging.sent[-1]["body"].lower()
