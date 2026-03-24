from __future__ import annotations

from datetime import timezone
from uuid import uuid4

from apron.domain.enums import ConversationState
from apron.domain.models import UserProfile
from apron.ports.clock import ClockPort
from apron.ports.messaging import MessagingPort
from apron.ports.repositories import UserRepository
from apron.services.inventory import InventoryService


class OnboardingService:
    def __init__(
        self,
        user_repo: UserRepository,
        inventory_service: InventoryService,
        messaging: MessagingPort,
        clock: ClockPort,
    ) -> None:
        self._user_repo = user_repo
        self._inventory_service = inventory_service
        self._messaging = messaging
        self._clock = clock
        self._pending_inventory: dict[str, list] = {}

    async def start(self, phone: str) -> UserProfile:
        now = self._clock.now().astimezone(timezone.utc)
        user = UserProfile(
            id=uuid4(),
            phone_number=phone,
            created_at=now,
            updated_at=now,
        )
        await self._user_repo.save(user)
        await self._messaging.send_text(
            phone,
            "Welcome to Apron! Send me a photo of your fridge to start onboarding.",
        )
        return user

    async def handle_step(
        self, user: UserProfile, message: str, image_b64: str | None = None
    ) -> UserProfile:
        step = user.onboarding_step
        normalized = message.strip().lower()

        if step == 0:
            if not image_b64:
                await self._messaging.send_text(
                    user.phone_number, "Please send a fridge photo so I can detect your inventory."
                )
                return user
            parsed = await self._inventory_service.parse_photo(user, image_b64, persist=False)
            if not parsed:
                await self._messaging.send_text(
                    user.phone_number,
                    "I couldn't detect clear items from that photo. Please send another one.",
                )
                return user
            self._pending_inventory[str(user.id)] = parsed
            names = ", ".join(item.name for item in parsed) or "nothing"
            await self._messaging.send_text(
                user.phone_number, f"I see: {names}. Is this correct? (yes/no)"
            )
            return await self._advance(user, 1)

        if step == 1:
            if image_b64:
                parsed = await self._inventory_service.parse_photo(user, image_b64, persist=False)
                if not parsed:
                    await self._messaging.send_text(
                        user.phone_number,
                        "I still couldn't read that well. Try one more photo with better lighting.",
                    )
                    return user
                self._pending_inventory[str(user.id)] = parsed
                names = ", ".join(item.name for item in parsed) or "nothing"
                await self._messaging.send_text(
                    user.phone_number, f"Updated: I now see {names}. Is this correct? (yes/no)"
                )
                return user

            if normalized in {"yes", "y", "correct"}:
                pending = self._pending_inventory.pop(str(user.id), [])
                if pending:
                    await self._inventory_service.save_items(user.id, pending)
                await self._messaging.send_text(user.phone_number, "Great. Any allergies?")
                return await self._advance(user, 2)
            await self._messaging.send_text(
                user.phone_number,
                "Got it. Send a new photo or corrections like: add 2 eggs, remove milk.",
            )
            return user

        if step == 2:
            allergies = [] if normalized == "none" else [v.strip() for v in message.split(",") if v.strip()]
            user = user.model_copy(update={"allergies": allergies})
            user = await self._save(user)
            await self._messaging.send_text(
                user.phone_number, "Dietary preferences? (vegetarian, halal, etc.)"
            )
            return await self._advance(user, 3)

        if step == 3:
            prefs = [] if normalized == "none" else [v.strip() for v in message.split(",") if v.strip()]
            user = user.model_copy(update={"dietary_preferences": prefs})
            user = await self._save(user)
            await self._messaging.send_text(user.phone_number, "How many people in your household?")
            return await self._advance(user, 4)

        if step == 4:
            try:
                size = int(normalized)
            except ValueError:
                await self._messaging.send_text(user.phone_number, "Please send a whole number.")
                return user
            user = user.model_copy(update={"household_size": max(size, 1)})
            user = await self._save(user)
            await self._messaging.send_text(user.phone_number, "Weekly food budget in EUR?")
            return await self._advance(user, 5)

        if step == 5:
            try:
                budget = float(normalized.replace("€", ""))
            except ValueError:
                await self._messaging.send_text(user.phone_number, "Please send a number, e.g. 100.")
                return user
            user = user.model_copy(update={"weekly_budget": budget})
            user = await self._save(user)
            await self._messaging.send_text(user.phone_number, "What cuisines do you love?")
            return await self._advance(user, 6)

        if step == 6:
            cuisines = [] if normalized == "none" else [v.strip() for v in message.split(",") if v.strip()]
            user = user.model_copy(update={"preferred_cuisines": cuisines})
            user = await self._save(user)
            await self._messaging.send_text(
                user.phone_number, "All set! Your first meal plan arrives Sunday. Reply OK to continue."
            )
            return await self._advance(user, 7)

        if step >= 7:
            user = user.model_copy(
                update={"conversation_state": ConversationState.IDLE, "onboarding_step": 0}
            )
            user = await self._save(user)
            await self._messaging.send_text(user.phone_number, "You're ready. Ask: what's for today?")
            return user

        return user

    async def _advance(self, user: UserProfile, step: int) -> UserProfile:
        user = user.model_copy(update={"onboarding_step": step})
        return await self._save(user)

    async def _save(self, user: UserProfile) -> UserProfile:
        now = self._clock.now().astimezone(timezone.utc)
        updated = user.model_copy(update={"updated_at": now})
        return await self._user_repo.update(updated)
