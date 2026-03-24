from __future__ import annotations

from typing import Any
from uuid import uuid4

from apron.domain.models import UserProfile
from apron.ports.messaging import MessagingPort
from apron.services.inventory import InventoryService
from apron.services.meal_planner import MealPlannerService
from apron.services.ordering import OrderingService

try:
    from google.adk.agents import Agent, InvocationContext
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.events.event import Event
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - optional dependency at runtime
    Agent = None  # type: ignore[assignment]
    InvocationContext = None  # type: ignore[assignment]
    InMemoryArtifactService = None  # type: ignore[assignment]
    InMemorySessionService = None  # type: ignore[assignment]
    Event = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


class AdkOrchestratorService:
    """ADK-backed tool-calling orchestrator for IDLE conversations."""

    def __init__(
        self,
        model: str,
        messaging: MessagingPort,
        inventory: InventoryService,
        planner: MealPlannerService,
        ordering: OrderingService,
    ) -> None:
        if Agent is None:
            raise RuntimeError("google-adk is not installed. Install package `google-adk`.")

        self._messaging = messaging
        self._inventory = inventory
        self._planner = planner
        self._ordering = ordering
        self._session_service = InMemorySessionService()
        self._artifact_service = InMemoryArtifactService()
        self._session_ids: dict[str, str] = {}
        self._active: dict[str, Any] = {}

        async def add_inventory(message: str) -> str:
            user: UserProfile = self._active["user"]
            items = await self._inventory.add_from_message(user, message)
            return f"Added {len(items)} inventory item(s)."

        async def parse_inventory_photo() -> str:
            user: UserProfile = self._active["user"]
            image_b64: str | None = self._active.get("image_b64")
            if not image_b64:
                return "No photo attached. Ask user to send a photo."
            items = await self._inventory.parse_photo(user, image_b64)
            return f"Parsed {len(items)} item(s) from photo."

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

        async def start_grocery_order() -> str:
            user: UserProfile = self._active["user"]
            await self._ordering.start_order(user)
            return "Started grocery order flow."

        async def order_delivery(message: str) -> str:
            user: UserProfile = self._active["user"]
            await self._ordering.order_delivery(user, message)
            return "Prepared delivery order options."

        async def get_shopping_list() -> str:
            user: UserProfile = self._active["user"]
            items = await self._inventory.get_shopping_list(user.id)
            if not items:
                return "Shopping list is empty."
            return "Shopping list: " + ", ".join(item.name for item in items)

        self._agent = Agent(
            name="apron_whatsapp_agent",
            model=model,
            instruction=(
                "You are Apron's WhatsApp assistant. Be concise and practical. "
                "Use tools whenever the user asks about inventory, cooking suggestions, "
                "today's meal, grocery ordering, delivery, or shopping list. "
                "If a photo is attached and user intent is about inventory, call parse_inventory_photo."
            ),
            tools=[
                add_inventory,
                parse_inventory_photo,
                get_today_meal,
                suggest_from_inventory,
                start_grocery_order,
                order_delivery,
                get_shopping_list,
            ],
        )

    async def handle_idle(self, user: UserProfile, text: str, image_b64: str | None = None) -> bool:
        self._active = {"user": user, "image_b64": image_b64, "text": text}
        session = await self._get_or_create_session(user)
        invocation_id = f"inv_{uuid4().hex}"
        user_content = genai_types.Content(
            role="user", parts=[genai_types.Part(text=text or "User sent an image.")]
        )
        session.events.append(Event(invocation_id=invocation_id, author="user", content=user_content))

        ctx = InvocationContext(
            invocation_id=invocation_id,
            agent=self._agent,
            session=session,
            artifact_service=self._artifact_service,
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

        reply = " ".join(p.strip() for p in response_parts if p.strip()).strip()
        if reply:
            await self._messaging.send_text(user.phone_number, reply)
            return True
        return False

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
