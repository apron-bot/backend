from __future__ import annotations

import logging
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
    from google.adk.agents.run_config import RunConfig
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.events.event import Event
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types
except Exception:
    Agent = None  # type: ignore[assignment]
    InvocationContext = None  # type: ignore[assignment]
    InMemoryArtifactService = None  # type: ignore[assignment]
    InMemorySessionService = None  # type: ignore[assignment]
    Event = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]
    RunConfig = None  # type: ignore[assignment]
    LiteLlm = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class AdkOrchestratorService:
    """Two-agent orchestrator: onboarding agent + conversation agent."""

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
        model_backend: str = "native",
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

        # ── Onboarding tools ──

        async def onboarding_step(message: str) -> str:
            """Advance onboarding by one step. Sends a reply directly to the user."""
            if self._active.get("_tool_called"):
                return "Already handled. Stop."
            self._active["_tool_called"] = True
            self._active["_msg_sent"] = True
            user: UserProfile = self._active["user"]
            image_b64: str | None = self._active.get("image_b64")
            await self._onboarding.handle_step(user, message, image_b64=image_b64)
            return "Done — reply sent to user. Respond with HANDLED and nothing else."

        # ── Conversation tools ──

        _guard_msg = "Already called a tool. Do NOT call any more tools. Reply to the user now."

        async def get_today_meal() -> str:
            """Check what meal is planned for today."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            user: UserProfile = self._active["user"]
            meal = await self._planner.get_today_meal(user.id)
            if not meal:
                return "No meal planned for today."
            return f"Tonight: {meal.recipe.name} ({meal.recipe.cook_time_minutes} min)."

        async def suggest_recipes() -> str:
            """Suggest recipes based on current inventory."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            user: UserProfile = self._active["user"]
            recipes = await self._planner.suggest_from_inventory(user.id)
            if not recipes:
                return "No recipe suggestions available from current inventory."
            return "You can cook: " + ", ".join(r.name for r in recipes)

        async def start_cooking() -> str:
            """Start a cooking session for today's planned meal. Sends instructions directly."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            self._active["_msg_sent"] = True
            user: UserProfile = self._active["user"]
            meal = await self._planner.get_today_meal(user.id)
            if not meal:
                return "No recipe to cook right now."
            await self._cooking.start(user, meal.recipe)
            return "Done — cooking instructions sent to user. Respond with HANDLED."

        async def cooking_step(message: str) -> str:
            """Handle a message during an active cooking session. Sends reply directly."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            self._active["_msg_sent"] = True
            user: UserProfile = self._active["user"]
            await self._cooking.handle_step(user, message)
            return "Done — reply sent to user. Respond with HANDLED."

        async def add_inventory(message: str) -> str:
            """Add or remove items from inventory based on user text. Sends confirmation directly."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            self._active["_msg_sent"] = True
            user: UserProfile = self._active["user"]
            await self._inventory.add_from_message(user, message)
            return "Done — confirmation sent to user. Respond with HANDLED."

        async def parse_inventory_photo() -> str:
            """Detect food items from a photo and add to inventory."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            user: UserProfile = self._active["user"]
            image_b64: str | None = self._active.get("image_b64")
            if not image_b64:
                return "No photo attached. Ask the user to send one."
            items = await self._inventory.parse_photo(user, image_b64)
            if not items:
                return "Couldn't detect clear items in the photo."
            return f"Added {len(items)} item(s): " + ", ".join(i.name for i in items)

        async def get_inventory() -> str:
            """Get the user's current kitchen inventory."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            user: UserProfile = self._active["user"]
            items = await self._inventory._repo.get_all(user.id)
            if not items:
                return "Inventory is empty."
            lines = [f"- {i.name}: {i.quantity} {i.unit}" for i in items]
            return "Current inventory:\n" + "\n".join(lines)

        async def get_shopping_list() -> str:
            """Get the current shopping list."""
            if self._active.get("_tool_called"):
                return _guard_msg
            self._active["_tool_called"] = True
            user: UserProfile = self._active["user"]
            items = await self._inventory.get_shopping_list(user.id)
            if not items:
                return "Shopping list is empty."
            return "Shopping list: " + ", ".join(item.name for item in items)

        # ── Build models ──

        adk_model: str | LiteLlm
        if model_backend == "litellm":
            if LiteLlm is None:
                raise RuntimeError("ADK LiteLlm model backend is unavailable.")
            adk_model = LiteLlm(model=model)
        else:
            adk_model = model

        # ── Agent 1: Onboarding ──

        self._onboarding_agent = Agent(
            name="bobby_onboarding",
            model=adk_model,
            instruction=(
                "You are Bobby, the friendly Apron cooking assistant on WhatsApp. "
                "You are guiding a new user through onboarding.\n\n"
                "# Message format\n"
                "You receive: onboarding_step=<N>; message=<TEXT>; has_image=<BOOL>\n\n"
                "# Rules\n"
                "1. Call onboarding_step ONCE with the user's message. It handles everything.\n"
                "2. After calling it, respond with exactly HANDLED. Nothing else.\n"
                "3. NEVER call onboarding_step more than once.\n"
            ),
            tools=[onboarding_step],
        )

        # ── Agent 2: Conversation ──

        self._conversation_agent = Agent(
            name="bobby_conversation",
            model=adk_model,
            instruction=(
                "You are Bobby, the friendly Apron cooking assistant on WhatsApp.\n\n"
                "# Message format\n"
                "You receive: state=<STATE>; message=<TEXT>; has_image=<BOOL>\n\n"
                "# Tool routing\n"
                "- User asks what's for today → get_today_meal\n"
                "- User wants recipe ideas → suggest_recipes\n"
                "- User wants to start cooking → start_cooking\n"
                "- state=cooking_mode → cooking_step\n"
                "- User adds/removes food items → add_inventory\n"
                "- has_image=True → parse_inventory_photo\n"
                "- User asks what's in their fridge/inventory → get_inventory\n"
                "- User asks about shopping list → get_shopping_list\n"
                "- Everything else → just reply, NO tool call\n\n"
                "# CRITICAL\n"
                "- You may call a tool AT MOST ONCE. After getting the tool result, "
                "you MUST immediately respond to the user with a text message. "
                "NEVER call the same tool again. NEVER call any tool a second time.\n"
                "- If a tool returns empty/no-data, tell the user in a friendly way. "
                "Do NOT retry the tool.\n"
                "- Tools marked 'sends reply directly' already messaged the user. "
                "Just respond with HANDLED.\n\n"
                "# Style: warm, casual, 1-3 sentences max.\n"
            ),
            tools=[
                get_today_meal,
                suggest_recipes,
                start_cooking,
                cooking_step,
                add_inventory,
                parse_inventory_photo,
                get_inventory,
                get_shopping_list,
            ],
        )

    async def handle_message(self, user: UserProfile, text: str, image_b64: str | None = None) -> bool:
        self._active = {
            "user": user,
            "image_b64": image_b64,
            "text": text,
        }

        # Route to the right agent
        if user.conversation_state == ConversationState.ONBOARDING:
            agent = self._onboarding_agent
            payload_text = (
                f"onboarding_step={user.onboarding_step}; "
                f"message={text or '[empty]'}; has_image={bool(image_b64)}"
            )
            logger.info("Routing to onboarding agent (step %d)", user.onboarding_step)
        else:
            agent = self._conversation_agent
            payload_text = (
                f"state={user.conversation_state.value}; "
                f"message={text or '[empty]'}; has_image={bool(image_b64)}"
            )
            logger.info("Routing to conversation agent (state=%s)", user.conversation_state.value)

        session = await self._get_or_create_session(user)
        invocation_id = f"inv_{uuid4().hex}"
        user_content = genai_types.Content(role="user", parts=[genai_types.Part(text=payload_text)])
        session.events.append(Event(invocation_id=invocation_id, author="user", content=user_content))

        ctx = InvocationContext(
            invocation_id=invocation_id,
            agent=agent,
            session=session,
            artifact_service=self._artifact_service,
            session_service=self._session_service,
            run_config=RunConfig(response_modalities=["TEXT"], max_llm_calls=5),
        )

        response_parts: list[str] = []
        try:
            async for event in agent.run_async(ctx):
                # Save event to session so the model sees it on next LLM call
                if not event.partial:
                    await self._session_service.append_event(session=session, event=event)

                if self._active.get("_msg_sent"):
                    break
                # Log tool calls
                content = getattr(event, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    for part in parts:
                        fc = getattr(part, "function_call", None)
                        if fc:
                            logger.info("Tool call: %s(%s)", fc.name, fc.args)
                        fr = getattr(part, "function_response", None)
                        if fr:
                            logger.info("Tool result: %s -> %s", fr.name, fr.response)
                        text_part = getattr(part, "text", None)
                        if text_part:
                            response_parts.append(text_part)
        except Exception:
            logger.exception("Agent run failed")

        if self._active.get("_msg_sent"):
            return True

        reply = " ".join(p.strip() for p in response_parts if p and p.strip()).strip()
        if not reply or reply.strip("[] ").upper() == "HANDLED":
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
