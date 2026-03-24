
from __future__ import annotations

import os
from functools import lru_cache

from apron.adapters.claude_llm import ClaudeLLMAdapter
from apron.adapters.gemini_llm import GeminiLLMAdapter
from apron.adapters.inmemory import (
    InMemoryClock,
    InMemoryInventoryRepository,
    InMemoryLLM,
    InMemoryMealPlanRepository,
    InMemoryMessaging,
    InMemoryOrderRepository,
    InMemoryOrdering,
    InMemoryRecipeRepository,
    InMemoryShoppingListRepository,
    InMemoryUserRepository,
)
from apron.adapters.twilio_whatsapp import TwilioWhatsAppAdapter
from apron.config import Settings
from apron.services.cooking import CookingSessionService
from apron.services.inventory import InventoryService
from apron.services.meal_planner import MealPlannerService
from apron.services.onboarding import OnboardingService
from apron.services.ordering import OrderingService
from apron.services.adk_orchestrator import AdkOrchestratorService
from apron.services.router import MessageRouterService
from apron.services.scheduler import ProactiveSchedulerService


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def _container() -> dict:
    settings = get_settings()
    llm_provider = settings.llm_provider.lower().strip()
    messaging_provider = settings.messaging_provider.lower().strip()

    user_repo = InMemoryUserRepository()
    if messaging_provider == "twilio":
        messaging = TwilioWhatsAppAdapter(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            settings.twilio_from_number,
        )
    else:
        messaging = InMemoryMessaging()

    if llm_provider == "gemini" and settings.gemini_api_key:
        llm = GeminiLLMAdapter(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            text_model=settings.gemini_text_model,
            vision_model=settings.gemini_vision_model,
        )
    elif llm_provider == "claude" and settings.anthropic_api_key:
        llm = ClaudeLLMAdapter(
            api_key=settings.anthropic_api_key,
            openai_api_key=settings.openai_api_key,
            model=settings.claude_model,
        )
    else:
        llm = InMemoryLLM()

    clock = InMemoryClock()
    inventory_repo = InMemoryInventoryRepository()
    plan_repo = InMemoryMealPlanRepository()
    recipe_repo = InMemoryRecipeRepository()
    shopping_repo = InMemoryShoppingListRepository()
    order_repo = InMemoryOrderRepository()
    ordering_port = InMemoryOrdering()

    inventory = InventoryService(inventory_repo, llm, messaging)
    planner = MealPlannerService(
        user_repo,
        inventory_repo,
        plan_repo,
        recipe_repo,
        llm,
        messaging,
        clock,
    )
    ordering = OrderingService(
        ordering_port,
        shopping_repo,
        order_repo,
        messaging,
        user_repo,
    )
    onboarding = OnboardingService(user_repo, inventory, messaging, clock)
    cooking = CookingSessionService(messaging, llm, inventory_repo, user_repo)
    adk_model = settings.gemini_text_model or settings.gemini_model
    if settings.gemini_api_key:
        # ADK/google-genai reads GOOGLE_API_KEY by default.
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
    adk_orchestrator = AdkOrchestratorService(
        model=adk_model,
        llm=llm,
        messaging=messaging,
        onboarding=onboarding,
        inventory=inventory,
        planner=planner,
        cooking=cooking,
        ordering=ordering,
    )
    router = MessageRouterService(
        user_repo,
        llm,
        messaging,
        onboarding,
        inventory,
        planner,
        cooking,
        ordering,
        adk_orchestrator=adk_orchestrator,
    )
    scheduler = ProactiveSchedulerService(user_repo, inventory, planner)
    return {
        "user_repo": user_repo,
        "inventory_repo": inventory_repo,
        "plan_repo": plan_repo,
        "recipe_repo": recipe_repo,
        "order_repo": order_repo,
        "shopping_repo": shopping_repo,
        "ordering_service": ordering,
        "scheduler": scheduler,
        "router": router,
        "inventory": inventory,
        "planner": planner,
    }


def get_router() -> MessageRouterService:
    return _container()["router"]


def get_inventory_repo():
    return _container()["inventory_repo"]


def get_plan_repo():
    return _container()["plan_repo"]


def get_recipe_repo():
    return _container()["recipe_repo"]


def get_order_repo():
    return _container()["order_repo"]


def get_user_repo():
    return _container()["user_repo"]


def get_planner() -> MealPlannerService:
    return _container()["planner"]


def get_scheduler() -> ProactiveSchedulerService:
    return _container()["scheduler"]
