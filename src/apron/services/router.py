
from __future__ import annotations

import logging

from apron.ports.llm import LLMPort
from apron.ports.messaging import MessagingPort
from apron.ports.repositories import UserRepository
from apron.services.cooking import CookingSessionService
from apron.services.inventory import InventoryService
from apron.services.meal_planner import MealPlannerService
from apron.services.onboarding import OnboardingService
from apron.services.ordering import OrderingService
from apron.services.adk_orchestrator import AdkOrchestratorService

logger = logging.getLogger(__name__)


class MessageRouterService:
    def __init__(
        self,
        user_repo: UserRepository,
        llm: LLMPort,
        messaging: MessagingPort,
        onboarding: OnboardingService,
        inventory: InventoryService,
        planner: MealPlannerService,
        cooking: CookingSessionService,
        ordering: OrderingService,
        adk_orchestrator: AdkOrchestratorService,
    ) -> None:
        self._user_repo = user_repo
        self._llm = llm
        self._messaging = messaging
        self._onboarding = onboarding
        self._inventory = inventory
        self._planner = planner
        self._cooking = cooking
        self._ordering = ordering
        self._adk_orchestrator = adk_orchestrator

    async def handle(self, phone: str, text: str, image_b64: str | None = None) -> None:
        try:
            user = await self._user_repo.get_by_phone(phone)
            if not user:
                user = await self._onboarding.start(phone)
            await self._adk_orchestrator.handle_message(user, text, image_b64=image_b64)
        except Exception:
            logger.exception("ADK router handling failed")
            try:
                await self._messaging.send_text(
                    phone, "I'm having trouble right now. Try again in a moment."
                )
            except Exception:
                return

