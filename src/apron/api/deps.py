
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
from apron.adapters.minimax_llm import MiniMaxLLMAdapter
from apron.adapters.openai_llm import OpenAILLMAdapter
from apron.adapters.telegram_messaging import TelegramMessagingAdapter
from apron.adapters.twilio_whatsapp import TwilioWhatsAppAdapter
from apron.api.streaming import get_event_bus as _get_event_bus
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
    adk_model_provider = settings.adk_model_provider.lower().strip()

    storage_backend = settings.storage_backend.lower().strip()
    if storage_backend == "sqlite":
        from apron.adapters.sqlite.repositories import (
            SqliteInventoryRepository,
            SqliteUserRepository,
        )
        user_repo = SqliteUserRepository(settings.sqlite_path)
        inventory_repo = SqliteInventoryRepository(settings.sqlite_path)
    else:
        user_repo = InMemoryUserRepository()
        inventory_repo = InMemoryInventoryRepository()

    if messaging_provider == "telegram":
        messaging = TelegramMessagingAdapter(
            bot_token=settings.telegram_bot_token,
        )
    elif messaging_provider == "twilio":
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
    elif llm_provider == "minimax" and settings.minimax_api_key:
        llm = MiniMaxLLMAdapter(
            api_key=settings.minimax_api_key,
            api_base=settings.minimax_api_base,
            text_model=settings.minimax_text_model,
            vision_model=settings.minimax_vision_model,
        )
    elif llm_provider == "openai" and settings.openai_api_key:
        llm = OpenAILLMAdapter(
            api_key=settings.openai_api_key,
            text_model=settings.openai_text_model,
            vision_model=settings.openai_vision_model,
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
    onboarding = OnboardingService(
        user_repo, inventory, messaging, clock,
        on_onboarding_complete=lambda user_id: planner.generate_weekly_plan(user_id),
    )
    cooking = CookingSessionService(messaging, llm, inventory_repo, user_repo)
    if adk_model_provider == "openai":
        adk_model = settings.openai_text_model
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        adk_model_backend = "litellm"
    elif adk_model_provider == "minimax":
        adk_model = settings.minimax_text_model
        if settings.minimax_api_key:
            os.environ["MINIMAX_API_KEY"] = settings.minimax_api_key
        if settings.minimax_api_base:
            os.environ["MINIMAX_API_BASE"] = settings.minimax_api_base
        adk_model_backend = "litellm"
    else:
        adk_model = settings.gemini_text_model or settings.gemini_model
        if settings.gemini_api_key:
            # ADK/google-genai reads GOOGLE_API_KEY by default.
            os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
        adk_model_backend = "native"
    adk_orchestrator = AdkOrchestratorService(
        model=adk_model,
        llm=llm,
        messaging=messaging,
        onboarding=onboarding,
        inventory=inventory,
        planner=planner,
        cooking=cooking,
        ordering=ordering,
        model_backend=adk_model_backend,
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


def get_event_bus():
    return _get_event_bus()
