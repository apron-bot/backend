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


class AdkOrchestratorService:
    """Simplified ADK orchestrator — onboarding + free chat."""

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

        # -- Single tool: onboarding --
        async def onboarding_step(message: str) -> str:
            """Advance the onboarding conversation by one step.

            Call this ONCE when state=onboarding. It sends a reply to the user
            directly — do NOT reply yourself after calling this.
            """
            if self._active.get("_tool_called"):
                return "Already handled. Stop."
            self._active["_tool_called"] = True
            user: UserProfile = self._active["user"]
            image_b64: str | None = self._active.get("image_b64")
            await self._onboarding.handle_step(user, message, image_b64=image_b64)
            return "Done — reply sent to user. Respond with HANDLED and nothing else."

        adk_model: str | LiteLlm
        if model_backend == "litellm":
            if LiteLlm is None:
                raise RuntimeError("ADK LiteLlm model backend is unavailable.")
            adk_model = LiteLlm(model=model)
        else:
            adk_model = model

        self._agent = Agent(
            name="apron_whatsapp_agent",
            model=adk_model,
            instruction=(
                "You are Bobby, the friendly Apron cooking assistant on WhatsApp. "
                "You help people set up their kitchen, plan meals, and cook.\n\n"
                "# Message format\n"
                "You receive: state=<STATE>; onboarding_step=<N>; message=<TEXT>; has_image=<BOOL>\n\n"
                "# Rules\n"
                "- If state=onboarding: call the onboarding_step tool with the user's message, "
                "then respond with exactly HANDLED. Do NOT add anything else. "
                "Do NOT call the tool more than once.\n"
                "- If state=idle (or any other state): reply directly to the user in a warm, "
                "concise style. Do NOT call any tools. Just chat.\n\n"
                "# Style\n"
                "- Keep replies short (1-3 sentences).\n"
                "- Be warm and casual, like a friend who loves cooking.\n"
                "- Use the user's name if you know it."
            ),
            tools=[onboarding_step],
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
            run_config=RunConfig(response_modalities=["TEXT"], max_llm_calls=3),
        )

        response_parts: list[str] = []
        async for event in self._agent.run_async(ctx):
            # Tool already sent a message — stop collecting.
            if self._active.get("_tool_called"):
                break
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                text_part = getattr(part, "text", None)
                if text_part:
                    response_parts.append(text_part)

        if self._active.get("_tool_called"):
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
