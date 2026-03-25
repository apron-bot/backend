from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)

from apron.domain.enums import MealType
from apron.domain.models import MealPlan, PlannedMeal, Recipe, RecipeIngredient
from apron.domain.rules import calculate_missing_ingredients, filter_safe_recipes
from apron.ports.clock import ClockPort
from apron.ports.llm import LLMPort
from apron.ports.messaging import MessagingPort
from apron.ports.repositories import (
    InventoryRepository,
    MealPlanRepository,
    RecipeRepository,
    UserRepository,
)


class MealPlannerService:
    def __init__(
        self,
        user_repo: UserRepository,
        inventory_repo: InventoryRepository,
        plan_repo: MealPlanRepository,
        recipe_repo: RecipeRepository,
        llm: LLMPort,
        messaging: MessagingPort,
        clock: ClockPort,
    ) -> None:
        self._user_repo = user_repo
        self._inventory_repo = inventory_repo
        self._plan_repo = plan_repo
        self._recipe_repo = recipe_repo
        self._llm = llm
        self._messaging = messaging
        self._clock = clock

    async def generate_weekly_plan(self, user_id):
        user = await self._user_repo.get_by_id(user_id)
        inventory = await self._inventory_repo.get_all(user_id)
        items_str = ", ".join(f"{i.name} ({i.quantity} {i.unit})" for i in inventory) or "none"
        prefs = ", ".join(user.dietary_preferences) or "none"
        allergies = ", ".join(user.allergies) or "none"
        cuisines = ", ".join(user.preferred_cuisines) or "any"
        raw = await self._llm.chat(
            "You are a meal planning engine. Generate a 7-day dinner plan. "
            "Return ONLY a JSON array of recipe objects. "
            "Each recipe must have: name, description, cuisine, cook_time_minutes, difficulty "
            "(beginner/intermediate/advanced), servings, ingredients (array of {name, quantity, unit}), "
            "and steps (array of strings).",
            [{"role": "user", "content": (
                f"Inventory: {items_str}\n"
                f"Allergies: {allergies}\n"
                f"Diet: {prefs}\n"
                f"Preferred cuisines: {cuisines}\n"
                f"Household size: {user.household_size}\n"
                f"Budget: €{user.weekly_budget}/week"
            )}],
        )
        logger.info("Meal plan LLM raw response: %s", raw[:500])
        recipes = self._recipes_from_json(raw)
        logger.info("Parsed %d recipes from LLM", len(recipes))
        safe_recipes = filter_safe_recipes(recipes, user)
        logger.info("After safety filter: %d recipes", len(safe_recipes))
        missing = calculate_missing_ingredients(safe_recipes, inventory)
        today = self._clock.today()
        meals = [
            PlannedMeal(day=today + timedelta(days=i), meal_type=MealType.DINNER, recipe=r)
            for i, r in enumerate(safe_recipes[:7])
        ]
        plan = MealPlan(
            id=uuid4(),
            user_id=user_id,
            week_start=today - timedelta(days=today.weekday()),
            meals=meals,
            total_estimated_cost=10.0 * len(meals),
            missing_ingredients=missing,
            created_at=self._clock.now(),
        )
        await self._plan_repo.save(plan)
        await self._messaging.send_text(user.phone_number, f"Your weekly plan is ready with {len(meals)} meals.")
        return plan

    async def get_today_meal(self, user_id):
        plan = await self._plan_repo.get_current(user_id)
        if not plan:
            return None
        today = self._clock.today()
        for meal in plan.meals:
            if meal.day == today and not meal.cooked and not meal.skipped:
                return meal
        return None

    async def send_daily_reminder(self, user_id):
        user = await self._user_repo.get_by_id(user_id)
        today_meal = await self.get_today_meal(user_id)
        if not today_meal:
            await self._messaging.send_text(user.phone_number, "No meal scheduled for today.")
            return
        await self._messaging.send_text(
            user.phone_number,
            f"Tonight: {today_meal.recipe.name} ({today_meal.recipe.cook_time_minutes} min). Reply COOK to start.",
        )

    async def swap_meal(self, user_id, day, meal_type, constraint):
        _ = constraint
        plan = await self._plan_repo.get_current(user_id)
        if not plan:
            raise ValueError("No active plan")
        replacement = Recipe(
            id=uuid4(),
            name="Quick Pasta",
            description="Fallback replacement",
            cuisine="italian",
            cook_time_minutes=20,
            difficulty=plan.meals[0].recipe.difficulty if plan.meals else "intermediate",
            servings=2,
            ingredients=[RecipeIngredient(name="pasta", quantity=200, unit="g")],
            steps=["Boil water", "Cook pasta"],
            image_url=None,
            tags=["quick"],
        )
        updated_meals: list[PlannedMeal] = []
        target = None
        for meal in plan.meals:
            if meal.day == day and meal.meal_type == meal_type:
                target = meal.model_copy(update={"recipe": replacement})
                updated_meals.append(target)
            else:
                updated_meals.append(meal)
        if not target:
            target = PlannedMeal(day=day, meal_type=meal_type, recipe=replacement)
            updated_meals.append(target)
        plan = plan.model_copy(update={"meals": updated_meals})
        await self._plan_repo.update(plan)
        return target

    async def suggest_from_inventory(self, user_id):
        inventory = await self._inventory_repo.get_all(user_id)
        if not inventory:
            return []
        items_str = ", ".join(f"{i.name} ({i.quantity} {i.unit})" for i in inventory)
        raw = await self._llm.chat(
            "You are a recipe suggestion engine. Given the user's available ingredients, "
            "suggest up to 3 recipes they can make. Return ONLY a JSON array of recipe objects. "
            "Each recipe must have: name, description, cuisine, cook_time_minutes, difficulty "
            "(beginner/intermediate/advanced), servings, ingredients (array of {name, quantity, unit}), "
            "and steps (array of strings).",
            [{"role": "user", "content": f"My ingredients: {items_str}"}],
        )
        return self._recipes_from_json(raw)[:3]

    async def rate_meal(self, user_id, meal_date, meal_type, rating):
        plan = await self._plan_repo.get_current(user_id)
        if not plan:
            return
        updated_meals: list[PlannedMeal] = []
        favorite_recipe = None
        for meal in plan.meals:
            if meal.day == meal_date and meal.meal_type == meal_type:
                updated_meals.append(meal.model_copy(update={"rating": rating}))
                favorite_recipe = meal.recipe if rating >= 4 else None
            else:
                updated_meals.append(meal)
        await self._plan_repo.update(plan.model_copy(update={"meals": updated_meals}))
        if favorite_recipe:
            await self._recipe_repo.save_favorite(user_id, favorite_recipe)

    async def handle_adjustment(self, user, message):
        _ = user
        _ = message
        return None

    def _recipes_from_json(self, raw: str) -> list[Recipe]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, dict):
            payload = payload.get("recipes") or payload.get("meals") or []
        recipes: list[Recipe] = []
        for idx, item in enumerate(payload):
            recipe_raw = item.get("recipe", item) if isinstance(item, dict) else {}
            if not isinstance(recipe_raw, dict):
                continue
            ingredients = [
                RecipeIngredient(
                    name=str(i.get("name", "")).lower(),
                    quantity=float(i.get("quantity", 1)),
                    unit=str(i.get("unit", "units")).lower(),
                )
                for i in recipe_raw.get("ingredients", [])
                if isinstance(i, dict) and i.get("name")
            ]
            if not recipe_raw.get("name"):
                continue
            recipes.append(
                Recipe(
                    id=uuid4(),
                    name=recipe_raw["name"],
                    description=recipe_raw.get("description", ""),
                    cuisine=recipe_raw.get("cuisine", "unknown"),
                    cook_time_minutes=int(recipe_raw.get("cook_time_minutes", 30)),
                    difficulty=recipe_raw.get("difficulty", "intermediate"),
                    servings=int(recipe_raw.get("servings", 2)),
                    ingredients=ingredients,
                    steps=list(recipe_raw.get("steps", ["Cook and serve"])),
                    image_url=recipe_raw.get("image_url"),
                    tags=list(recipe_raw.get("tags", [])),
                )
            )
            if idx > 20:
                break
        return recipes
