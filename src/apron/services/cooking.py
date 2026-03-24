
from __future__ import annotations

from apron.domain.enums import ConversationState
from apron.domain.models import Recipe, UserProfile
from apron.ports.llm import LLMPort
from apron.ports.messaging import MessagingPort
from apron.ports.repositories import InventoryRepository, UserRepository


class CookingSessionService:
    def __init__(
        self,
        messaging: MessagingPort,
        llm: LLMPort,
        inventory_repo: InventoryRepository,
        user_repo: UserRepository,
    ) -> None:
        self._messaging = messaging
        self._llm = llm
        self._inventory_repo = inventory_repo
        self._user_repo = user_repo
        self._state: dict[str, dict] = {}

    async def start(self, user: UserProfile, recipe: Recipe) -> None:
        self._state[str(user.id)] = {"recipe": recipe, "current_step": 0}
        await self._user_repo.update(user.model_copy(update={"conversation_state": ConversationState.COOKING_MODE}))
        await self._messaging.send_text(user.phone_number, f"Let's cook {recipe.name}. Reply NEXT when ready.")
        await self._messaging.send_text(user.phone_number, f"Step 1: {recipe.steps[0] if recipe.steps else 'Start cooking.'}")

    async def handle_step(self, user: UserProfile, message: str) -> None:
        st = self._state.get(str(user.id))
        if not st:
            await self._messaging.send_text(user.phone_number, "No active cooking session.")
            return
        recipe: Recipe = st["recipe"]
        msg = message.strip().lower()
        idx = st["current_step"]

        if msg in {"next", "done"}:
            idx += 1
            if idx >= len(recipe.steps):
                await self.end_session(user)
                return
            st["current_step"] = idx
            await self._messaging.send_text(user.phone_number, f"Step {idx + 1}: {recipe.steps[idx]}")
            return

        if msg == "repeat":
            await self._messaging.send_text(user.phone_number, f"Step {idx + 1}: {recipe.steps[idx]}")
            return

        if msg.startswith("substitute"):
            reply = await self._llm.chat(
                "You are a cooking substitution assistant.",
                [{"role": "user", "content": f"recipe={recipe.name} message={message}"}],
            )
            await self._messaging.send_text(user.phone_number, reply)
            return

        answer = await self._llm.chat(
            "You are a concise cooking coach.",
            [{"role": "user", "content": f"recipe={recipe.name} step={idx+1} question={message}"}],
        )
        await self._messaging.send_text(user.phone_number, answer)

    async def end_session(self, user: UserProfile) -> None:
        self._state.pop(str(user.id), None)
        await self._user_repo.update(user.model_copy(update={"conversation_state": ConversationState.IDLE}))
        await self._messaging.send_text(user.phone_number, "Great job. Meal finished! Rate it 1-5.")
