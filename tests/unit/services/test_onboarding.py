
from __future__ import annotations

import json

from apron.domain.enums import ConversationState
from apron.services.inventory import InventoryService
from apron.services.onboarding import OnboardingService


async def test_start_creates_user_and_sends_welcome(fake_clock):
    from tests.conftest import FakeInventoryRepository, FakeLLM, FakeMessaging, FakeUserRepository

    user_repo = FakeUserRepository()
    messaging = FakeMessaging()
    inventory_service = InventoryService(FakeInventoryRepository(), FakeLLM(), messaging)
    svc = OnboardingService(user_repo, inventory_service, messaging, fake_clock)

    user = await svc.start("+34611111111")
    assert user.onboarding_step == 0
    assert user.conversation_state == ConversationState.ONBOARDING
    assert messaging.sent[-1]["body"].startswith("Welcome")


async def test_step0_photo_parses_inventory(fake_clock):
    from tests.conftest import FakeInventoryRepository, FakeLLM, FakeMessaging, FakeUserRepository

    llm = FakeLLM({"fridge inventory parse": json.dumps([{"name": "milk", "quantity": 1000, "unit": "ml"}])})
    user_repo = FakeUserRepository()
    messaging = FakeMessaging()
    inventory_repo = FakeInventoryRepository()
    inventory = InventoryService(inventory_repo, llm, messaging)
    svc = OnboardingService(user_repo, inventory, messaging, fake_clock)

    user = await svc.start("+34622222222")
    user = await svc.handle_step(user, "", image_b64="abc")

    assert user.onboarding_step == 1
    assert "I see:" in messaging.sent[-1]["body"]


async def test_step1_rejection_reprompts(fake_clock):
    from tests.conftest import FakeInventoryRepository, FakeLLM, FakeMessaging, FakeUserRepository

    user_repo = FakeUserRepository()
    messaging = FakeMessaging()
    inventory = InventoryService(FakeInventoryRepository(), FakeLLM(), messaging)
    svc = OnboardingService(user_repo, inventory, messaging, fake_clock)
    user = await svc.start("+34633333333")
    user = await user_repo.update(user.model_copy(update={"onboarding_step": 1}))

    same = await svc.handle_step(user, "no")
    assert same.onboarding_step == 1
    assert "Send corrections" in messaging.sent[-1]["body"]


async def test_completion_sets_state_idle(fake_clock):
    from tests.conftest import FakeInventoryRepository, FakeLLM, FakeMessaging, FakeUserRepository

    user_repo = FakeUserRepository()
    messaging = FakeMessaging()
    inventory = InventoryService(FakeInventoryRepository(), FakeLLM(), messaging)
    svc = OnboardingService(user_repo, inventory, messaging, fake_clock)
    user = await svc.start("+34644444444")
    user = await user_repo.update(user.model_copy(update={"onboarding_step": 7}))

    completed = await svc.handle_step(user, "ok")
    assert completed.conversation_state == ConversationState.IDLE
    assert completed.onboarding_step == 0


async def test_skip_optional_fields(fake_clock):
    from tests.conftest import FakeInventoryRepository, FakeLLM, FakeMessaging, FakeUserRepository

    user_repo = FakeUserRepository()
    messaging = FakeMessaging()
    inventory = InventoryService(FakeInventoryRepository(), FakeLLM(), messaging)
    svc = OnboardingService(user_repo, inventory, messaging, fake_clock)
    user = await svc.start("+34655555555")
    user = await user_repo.update(user.model_copy(update={"onboarding_step": 2}))

    user = await svc.handle_step(user, "none")
    assert user.allergies == []
    user = await svc.handle_step(user, "none")
    assert user.dietary_preferences == []
