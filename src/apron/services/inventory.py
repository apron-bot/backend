from __future__ import annotations

import json
import logging
from datetime import date
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

from apron.domain.enums import IngredientSource
from apron.domain.models import InventoryItem, Recipe, ShoppingListItem, UserProfile
from apron.domain.rules import get_low_stock_items, subtract_ingredients
from apron.ports.llm import LLMPort
from apron.ports.messaging import MessagingPort
from apron.ports.repositories import InventoryRepository


PHOTO_PROMPT = """You are a kitchen inventory assistant. Analyze this fridge/pantry photo.
List every visible food item with estimated quantity.
Return ONLY a JSON array."""

MESSAGE_PROMPT = """Extract inventory items from user text.
Return ONLY JSON array: [{"name":"...", "quantity": 1, "unit":"units"}]"""


class InventoryService:
    def __init__(self, repo: InventoryRepository, llm: LLMPort, messaging: MessagingPort):
        self._repo = repo
        self._llm = llm
        self._messaging = messaging
        self._shopping: dict[str, list[ShoppingListItem]] = {}

    async def parse_photo(
        self, user: UserProfile, image_b64: str, persist: bool = True
    ) -> list[InventoryItem]:
        try:
            raw = await self._llm.vision("fridge inventory parse", image_b64, PHOTO_PROMPT)
            logger.info("Vision LLM raw response: %s", raw)
        except Exception:
            logger.exception("Vision LLM call failed")
            await self._messaging.send_text(
                user.phone_number,
                "I had trouble reading that photo. Please try again with a clearer image.",
            )
            return []
        parsed = self._safe_json(raw)
        logger.info("Parsed items: %s", parsed)
        items = [
            InventoryItem(
                id=uuid4(),
                user_id=user.id,
                name=str(item.get("name", "")).strip().lower(),
                quantity=float(item.get("quantity", 1)),
                unit=str(item.get("unit", "units")).strip().lower(),
                expiry_date=self._parse_expiry(item.get("estimated_expiry")),
                date_added=user.updated_at,
                source=IngredientSource.PHOTO_PARSE,
            )
            for item in parsed
            if item.get("name")
        ]
        if persist and items:
            await self._repo.bulk_upsert(items)
        return items

    async def add_from_message(self, user: UserProfile, message: str) -> list[InventoryItem]:
        raw = await self._llm.chat(MESSAGE_PROMPT, [{"role": "user", "content": message}])
        parsed = self._safe_json(raw)
        if not parsed:
            token = message.strip().lower().split()[-1] if message.strip() else "item"
            parsed = [{"name": token, "quantity": 1, "unit": "units"}]
        items = [
            InventoryItem(
                id=uuid4(),
                user_id=user.id,
                name=str(item.get("name", "")).strip().lower(),
                quantity=float(item.get("quantity", 1)),
                unit=str(item.get("unit", "units")).strip().lower(),
                expiry_date=None,
                date_added=user.updated_at,
                source=IngredientSource.MANUAL,
            )
            for item in parsed
            if item.get("name")
        ]
        if items:
            await self._repo.bulk_upsert(items)
            await self._messaging.send_text(user.phone_number, f"Added {len(items)} item(s) to inventory.")
        return items

    async def subtract_recipe(self, user_id: UUID, recipe: Recipe) -> None:
        current = await self._repo.get_all(user_id)
        updated = subtract_ingredients(current, recipe)
        await self._repo.bulk_upsert(updated)

    async def check_low_stock(self, user_id: UUID) -> list[InventoryItem]:
        current = await self._repo.get_all(user_id)
        low = get_low_stock_items(current, {"rice": 200, "milk": 500, "egg": 4, "eggs": 4})
        return low

    async def get_shopping_list(self, user_id: UUID) -> list[ShoppingListItem]:
        return self._shopping.get(str(user_id), [])

    async def add_to_shopping_list(self, user_id: UUID, items: list[ShoppingListItem]) -> None:
        self._shopping.setdefault(str(user_id), []).extend(items)

    async def save_items(self, user_id: UUID, items: list[InventoryItem]) -> None:
        _ = user_id
        await self._repo.bulk_upsert(items)

    @staticmethod
    def _safe_json(raw: str) -> list[dict]:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]  # drop ```json line
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                return []
            results = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                # Normalise: accept "item" or "name" as the item name key
                if "name" not in item and "item" in item:
                    item["name"] = item.pop("item")
                results.append(item)
            return results
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _parse_expiry(raw: str | None) -> date | None:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
