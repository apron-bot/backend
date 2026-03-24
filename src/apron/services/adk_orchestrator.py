from __future__ import annotations

from typing import Any
from uuid import uuid4

from apron.domain.enums import ConversationState
from apron.domain.models import UserProfile
from apron.ports.llm import LLMPort
from apron.ports.messaging import MessagingPort
from apron.services.cooking import CookingSessionService
from apron.services.inventory import InventoryService
from apron.services.meal_planner import MealPlannerService
from apron.services.onboarding import OnboardingService
from apron.services.ordering import OrderingService

try:
    from google.adk.agents import Agent, InvocationContext
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.events.event import Event
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
except Exception:
    Agent = None  # type: ignore[assignment]
    InvocationContext = None  # type: ignore[assignment]
    InMemoryArtifactService = None  # type: ignore[assignment]
    InMemorySessionService = None  # type: ignore[assignment]
    Event = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


class AdkOrchestratorService:
    """ADK-first orchestrator for all conversation states."""

    def __init__(
        self,
        model: str,
        llm: LLMPort,
        messaging: MessagingPort,
        onboarding: OnboardingService,
        inventory: InventoryService,
        planner: MealPlannerService,
        cooking: CookingSessionService,
        ordering: OrderingService,
    ) -> None:
        if Agent is None:
            raise RuntimeError("google-adk is not installed. Install package `google-adk`.")

        self._llm = llm
        self._messaging = messaging
        self._onboarding = onboarding
        self._inventory = inventory
        self._planner = planner
        self._cooking = cooking
        self._ordering = ordering
        self._session_service = InMemorySessionService()
        self._artifact_service = InMemoryArtifactService()
        self._session_ids: dict[str, str] = {}
        self._active: dict[str, Any] = {}

        async def onboarding_step(message: str) -> str:
            user: UserProfile = self._active["user"]
            image_b64: str | None = self._active.get("image_b64")
            await self._onboarding.handle_step(user, message, image_b64=image_b64)
            return "[HANDLED]"

        async def cooking_step(message: str) -> str:
            user: UserProfile = self._active["user"]
            await self._cooking.handle_step(user, message)
            return "[HANDLED]"

        async def ordering_step(message: str) -> str:
            user: UserProfile = self._active["user"]
            await self._ordering.handle(user, message)
            return "[HANDLED]"

        async def adjust_plan_step(message: str) -> str:
            user: UserProfile = self._active["user"]
            await self._planner.handle_adjustment(user, message)
            return "[HANDLED]"

        async def add_inventory(message: str) -> str:
            user: UserProfile = self._active["user"]
            await self._inventory.add_from_message(user, message)
            return "[HANDLED]"

        async def parse_inventory_photo() -> str:
            user: UserProfile = self._active["user"]
            image_b64: str | None = self._active.get("image_b64")
            if not image_b64:
                return "No photo attached. Ask the user to send a photo."
            items = await self._inventory.parse_photo(user, image_b64)
            if not items:
                return "I could not detect clear items in the photo."
            return f"Added {len(items)} item(s) from photo."

        async def get_today_meal() -> str:
            user: UserProfile = self._active["user"]
            meal = await self._planner.get_today_meal(user.id)
            if not meal:
                return "No meal planned for today."
            return f"Tonight: {meal.recipe.name} ({meal.recipe.cook_time_minutes} min)."

        async def suggest_from_inventory() -> str:
            user: UserProfile = self._active["user"]
            recipes = await self._planner.suggest_from_inventory(user.id)
            if not recipes:
                return "No recipe suggestions available from current inventory."
            return "You can cook: " + ", ".join(r.name for r in recipes)

        async def start_cooking_today() -> str:
            user: UserProfile = self._active["user"]
            meal = await self._planner.get_today_meal(user.id)
            if not meal:
                return "No recipe to cook right now."
            await self._cooking.start(user, meal.recipe)
            return "[HANDLED]"

        async def start_grocery_order() -> str:
            user: UserProfile = self._active["user"]
            await self._ordering.start_order(user)
            return "[HANDLED]"

        async def order_delivery(message: str) -> str:
            user: UserProfile = self._active["user"]
            await self._ordering.order_delivery(user, message)
            return "[HANDLED]"

        async def get_shopping_list() -> str:
            user: UserProfile = self._active["user"]
            items = await self._inventory.get_shopping_list(user.id)
            if not items:
                return "Shopping list is empty."
            return "Shopping list: " + ", ".join(item.name for item in items)

        async def answer_general_question(message: str) -> str:
            return await self._llm.chat(
                "You are Apron, a concise cooking assistant.",
                [{"role": "user", "content": message}],
            )

        self._agent = Agent(
            name="apron_whatsapp_agent",
            model=model,
            instruction=(
                "You are Apron's WhatsApp brain. Always follow conversation_state and onboarding_step. "
                "Tool-routing policy: "
                "- onboarding => call onboarding_step(message). "
                "- cooking_mode => call cooking_step(message). "
                "- ordering_mode => call ordering_step(message). "
                "- adjusting_plan => call adjust_plan_step(message). "
                "- idle with photo => call parse_inventory_photo. "
                "- idle inventory text => add_inventory. "
                "- idle meal question => get_today_meal or suggest_from_inventory. "
                "- idle cooking start => start_cooking_today. "
                "- idle groceries => start_grocery_order or order_delivery. "
                "- shopping list => get_shopping_list. "
                "- fallback => answer_general_question. "
                "If a tool returns [HANDLED], reply exactly [HANDLED] and nothing else."
            ),
            tools=[
                onboarding_step,
                cooking_step,
                ordering_step,
                adjust_plan_step,
                add_inventory,
                parse_inventory_photo,
                get_today_meal,
                suggest_from_inventory,
                start_cooking_today,
                start_grocery_order,
                order_delivery,
                get_shopping_list,
                answer_general_question,
            ],
        )

    async def handle_message(self, user: UserProfile, text: str, image_b64: str | None = None) -> bool:
        self._active = {
            "user": user,
            "image_b64": image_b64,
            "text": text,
            "conversation_state": user.conversation_state.value,
            "onboarding_step": user.onboarding_step,
        }
        session = await self._get_or_create_session(user)
        invocation_id = f"inv_{uuid4().hex}"
        payload_text = (
            f"state={user.conversation_state.value}; onboarding_step={user.onboarding_step}; "
            f"message={text or '[empty]'}; has_image={bool(image_b64)}"
        )
        user_content = genai_types.Content(role="user", parts=[genai_types.Part(text=payload_text)])
        session.events.append(Event(invocation_id=invocation_id, author="user", content=user_content))

        ctx = InvocationContext(
            invocation_id=invocation_id,
            agent=self._agent,
            session=session,
            artifact_service=self._artifact_service,
            session_service=self._session_service,
        )

        response_parts: list[str] = []
        async for event in self._agent.run_async(ctx):
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                text_part = getattr(part, "text", None)
                if text_part:
                    response_parts.append(text_part)

        reply = " ".join(p.strip() for p in response_parts if p and p.strip()).strip()
        if not reply or reply == "[HANDLED]":
            return True
        await self._messaging.send_text(user.phone_number, reply)
        return True

    async def _get_or_create_session(self, user: UserProfile):
        key = str(user.id)
        if key in self._session_ids:
            existing = await self._session_service.get_session(
                app_name="apron_adk",
                user_id=key,
                session_id=self._session_ids[key],
            )
            if existing:
                return existing

        created = await self._session_service.create_session(app_name="apron_adk", user_id=key)
        self._session_ids[key] = created.id
        return created
