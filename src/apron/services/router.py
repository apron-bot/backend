
from __future__ import annotations

import json

from apron.domain.enums import ConversationState
from apron.ports.llm import LLMPort
from apron.ports.messaging import MessagingPort
from apron.ports.repositories import UserRepository
from apron.services.cooking import CookingSessionService
from apron.services.inventory import InventoryService
from apron.services.meal_planner import MealPlannerService
from apron.services.onboarding import OnboardingService
from apron.services.ordering import OrderingService


INTENT_SYSTEM_PROMPT = """Classify intent and return JSON: {"intent": str, "entities": dict}.
Allowed intents: add_inventory, photo_inventory, whats_for_today, cook_now,
swap_meal, what_can_i_cook, order_groceries, order_delivery, shopping_list,
rate_meal, general_question, unknown."""


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
    ) -> None:
        self._user_repo = user_repo
        self._llm = llm
        self._messaging = messaging
        self._onboarding = onboarding
        self._inventory = inventory
        self._planner = planner
        self._cooking = cooking
        self._ordering = ordering

    async def handle(self, phone: str, text: str, image_b64: str | None = None) -> None:
        try:
            user = await self._user_repo.get_by_phone(phone)
            if not user:
                user = await self._onboarding.start(phone)
                if text.strip() or image_b64:
                    user = await self._onboarding.handle_step(user, text, image_b64=image_b64)
                return

            if user.conversation_state == ConversationState.ONBOARDING:
                await self._onboarding.handle_step(user, text, image_b64=image_b64)
                return

            if user.conversation_state == ConversationState.COOKING_MODE:
                await self._cooking.handle_step(user, text)
                return

            if user.conversation_state == ConversationState.ORDERING_MODE:
                await self._ordering.handle(user, text)
                return

            if user.conversation_state == ConversationState.ADJUSTING_PLAN:
                await self._planner.handle_adjustment(user, text)
                return

            # Image-only messages should still work in idle mode.
            if image_b64 and not text.strip():
                items = await self._inventory.parse_photo(user, image_b64)
                if items:
                    await self._messaging.send_text(
                        user.phone_number, f"Added {len(items)} item(s) from your photo."
                    )
                return

            intent_payload = await self._llm.chat(
                INTENT_SYSTEM_PROMPT,
                [{"role": "user", "content": text}],
            )
            intent, entities = self._parse_intent(intent_payload)

            if intent == "add_inventory":
                await self._inventory.add_from_message(user, text)
                return
            if intent == "photo_inventory" and image_b64:
                items = await self._inventory.parse_photo(user, image_b64)
                if items:
                    await self._messaging.send_text(
                        user.phone_number, f"Added {len(items)} item(s) from your photo."
                    )
                return
            if intent == "whats_for_today":
                meal = await self._planner.get_today_meal(user.id)
                if meal:
                    await self._messaging.send_text(user.phone_number, f"Tonight: {meal.recipe.name}")
                else:
                    await self._messaging.send_text(user.phone_number, "No meal found for today.")
                return
            if intent == "cook_now":
                meal = await self._planner.get_today_meal(user.id)
                if meal:
                    await self._cooking.start(user, meal.recipe)
                else:
                    await self._messaging.send_text(user.phone_number, "No recipe to cook right now.")
                return
            if intent == "swap_meal":
                await self._messaging.send_text(user.phone_number, "Tell me which day and meal to swap.")
                return
            if intent == "what_can_i_cook":
                recipes = await self._planner.suggest_from_inventory(user.id)
                names = ", ".join(r.name for r in recipes) or "nothing right now"
                await self._messaging.send_text(user.phone_number, f"You can cook: {names}")
                return
            if intent == "order_groceries":
                await self._ordering.start_order(user)
                return
            if intent == "order_delivery":
                await self._ordering.order_delivery(user, text)
                return
            if intent == "shopping_list":
                items = await self._inventory.get_shopping_list(user.id)
                names = ", ".join(i.name for i in items) or "empty"
                await self._messaging.send_text(user.phone_number, f"Shopping list: {names}")
                return
            if intent == "general_question":
                answer = await self._llm.chat(
                    "Answer cooking question briefly.", [{"role": "user", "content": text}]
                )
                await self._messaging.send_text(user.phone_number, answer)
                return

            _ = entities
            await self._messaging.send_text(
                user.phone_number,
                "I didn't get that. Try: add inventory, what's for today, cook now, or order groceries.",
            )
        except Exception:
            try:
                await self._messaging.send_text(
                    phone, "I'm having trouble right now. Try again in a moment."
                )
            except Exception:
                return

    @staticmethod
    def _parse_intent(payload: str) -> tuple[str, dict]:
        try:
            data = json.loads(payload)
            return str(data.get("intent", "unknown")), data.get("entities", {})
        except json.JSONDecodeError:
            return "unknown", {}
