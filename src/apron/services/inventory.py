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


PHOTO_PROMPT = """You are a kitchen inventory assistant analyzing a photo of a fridge, pantry, or kitchen counter.

Your task: build a DETAILED grocery inventory from this photo.

Rules:
- Identify every food item by its standard grocery name (e.g. "whole milk", "eggs", "Greek yogurt", "cheddar cheese", "chicken breast").
- NEVER describe containers or packaging. "Small yellow container" is WRONG — identify what's INSIDE it. If it looks like butter, say "butter". If it looks like hummus, say "hummus".
- If you can read any label or brand name, use it (e.g. "Danone vanilla yogurt" instead of just "yogurt").
- Be SPECIFIC about quantities — count individual items where possible:
  - Eggs: count them (e.g. 6 units, not "some eggs")
  - Bottles/cartons: estimate volume (e.g. 1000 ml, 500 ml)
  - Fruits/vegetables: count them (e.g. 3 units of apples)
  - Packaged items: estimate weight if visible (e.g. 200 g)
- Use sensible units: "units" for countable items, "ml" or "liters" for liquids, "g" or "kg" for solids.
- If you see multiple of the same item, combine them into one entry with the total quantity.
- Skip non-food items (cleaning products, containers with unknown contents that you truly cannot guess).
- Estimate expiry date if visible on packaging (format: YYYY-MM-DD).

Return ONLY a JSON array: [{"name": "whole milk", "quantity": 1000, "unit": "ml", "estimated_expiry": "2026-04-15"}, ...]"""

MESSAGE_PROMPT = """Extract inventory items from user text.
Return ONLY JSON array: [{"name":"...", "quantity": 1, "unit":"units"}]"""

CONSUMED_TEXT_PROMPT = """The user says they ate or used some food. Extract what was consumed.
Return ONLY a JSON array: [{"name":"...", "quantity": 1, "unit":"units"}]
Use reasonable estimates if quantities aren't specified (e.g. "I ate eggs" → 2 eggs)."""

CONSUMED_PHOTO_PROMPT = """Analyze this photo of a meal that was eaten. Identify the ingredients
that were likely used to make this dish and estimate quantities consumed.
Return ONLY a JSON array: [{"name":"...", "quantity": 1, "unit":"units"}]"""


class InventoryService:
    def __init__(self, repo: InventoryRepository, llm: LLMPort, messaging: MessagingPort, shopping_repo=None):
        self._repo = repo
        self._llm = llm
        self._messaging = messaging
        self._shopping_repo = shopping_repo

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
        logger.info("Adding inventory from message: user=%s message=%r", user.id, message[:100])
        raw = await self._llm.chat(MESSAGE_PROMPT, [{"role": "user", "content": message}])
        parsed = self._safe_json(raw)
        logger.info("Parsed %d items from message for user=%s", len(parsed), user.id)
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

    async def log_consumed(
        self, user: UserProfile, message: str, image_b64: str | None = None
    ) -> list[str]:
        """Parse what the user ate (from text or meal photo) and subtract from inventory."""
        logger.info("Logging consumed: user=%s message=%r has_image=%s", user.id, message[:100], bool(image_b64))
        if image_b64:
            try:
                raw = await self._llm.vision("meal consumed parse", image_b64, CONSUMED_PHOTO_PROMPT)
            except Exception:
                return []
        else:
            raw = await self._llm.chat(
                CONSUMED_TEXT_PROMPT, [{"role": "user", "content": message}]
            )
        parsed = self._safe_json(raw)
        if not parsed:
            return []

        current = await self._repo.get_all(user.id)
        updated: list[InventoryItem] = []
        deleted: list[UUID] = []
        consumed_names: list[str] = []

        for entry in parsed:
            name = str(entry.get("name", "")).strip().lower()
            qty = float(entry.get("quantity", 1))
            if not name:
                continue
            consumed_names.append(name)
            match = self._fuzzy_match(name, current)
            if match:
                new_qty = max(0, match.quantity - qty)
                if new_qty > 0:
                    updated.append(match.model_copy(update={"quantity": new_qty}))
                else:
                    deleted.append(match.id)

        if updated:
            await self._repo.bulk_upsert(updated)
        for item_id in deleted:
            await self._repo.delete(item_id)
        return consumed_names

    @staticmethod
    def _fuzzy_match(name: str, items: list[InventoryItem]) -> InventoryItem | None:
        """Match consumed item name against inventory using fuzzy containment."""
        name = name.lower().rstrip("s")  # normalise plural: eggs→egg, bananas→banana
        for item in items:
            inv = item.name.lower().rstrip("s")
            if name == inv or name in inv or inv in name:
                return item
        return None

    async def subtract_recipe(self, user_id: UUID, recipe: Recipe) -> None:
        current = await self._repo.get_all(user_id)
        updated = subtract_ingredients(current, recipe)
        await self._repo.bulk_upsert(updated)

    async def check_low_stock(self, user_id: UUID) -> list[InventoryItem]:
        current = await self._repo.get_all(user_id)
        low = get_low_stock_items(current, {"rice": 200, "milk": 500, "egg": 4, "eggs": 4})
        return low

    async def get_shopping_list(self, user_id: UUID) -> list[ShoppingListItem]:
        if self._shopping_repo:
            return await self._shopping_repo.get_list(user_id)
        return []

    async def add_to_shopping_list(self, user_id: UUID, items: list[ShoppingListItem]) -> None:
        if self._shopping_repo:
            await self._shopping_repo.add_items(items)

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
