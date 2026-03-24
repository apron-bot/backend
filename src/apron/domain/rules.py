from __future__ import annotations

from collections import defaultdict
from datetime import date

from apron.domain.enums import TimeAvailability
from apron.domain.models import InventoryItem, Recipe, RecipeIngredient, UserProfile


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def contains_allergen(recipe: Recipe, allergies: list[str]) -> bool:
    allergies_n = [_normalize(a) for a in allergies if a.strip()]
    for ingredient in recipe.ingredients:
        iname = _normalize(ingredient.name)
        for allergy in allergies_n:
            if allergy in iname or iname in allergy:
                return True
    return False


def filter_safe_recipes(recipes: list[Recipe], user: UserProfile) -> list[Recipe]:
    disliked = {_normalize(item) for item in user.disliked_ingredients}
    safe: list[Recipe] = []
    for recipe in recipes:
        if contains_allergen(recipe, user.allergies):
            continue
        if any(_normalize(ing.name) in disliked for ing in recipe.ingredients):
            continue
        safe.append(recipe)
    return safe


def sort_by_expiry_priority(inventory: list[InventoryItem]) -> list[InventoryItem]:
    def key(item: InventoryItem) -> tuple[date, int, str]:
        return (item.expiry_date or date.max, 0 if item.expiry_date else 1, item.name)

    return sorted(inventory, key=key)


def calculate_missing_ingredients(
    recipes: list[Recipe], inventory: list[InventoryItem]
) -> list[RecipeIngredient]:
    inv_qty: dict[tuple[str, str], float] = defaultdict(float)
    for item in inventory:
        inv_qty[(_normalize(item.name), _normalize(item.unit))] += item.quantity

    needed: dict[tuple[str, str], float] = defaultdict(float)
    for recipe in recipes:
        for ing in recipe.ingredients:
            needed[(_normalize(ing.name), _normalize(ing.unit))] += ing.quantity

    missing: list[RecipeIngredient] = []
    for (name, unit), quantity in sorted(needed.items()):
        shortfall = quantity - inv_qty.get((name, unit), 0)
        if shortfall > 0:
            missing.append(RecipeIngredient(name=name, quantity=round(shortfall, 2), unit=unit))
    return missing


def is_within_budget(plan_cost: float, weekly_budget: float) -> bool:
    return plan_cost <= weekly_budget


def can_cook_now(
    recipe: Recipe, inventory: list[InventoryItem]
) -> tuple[bool, list[RecipeIngredient]]:
    missing = calculate_missing_ingredients([recipe], inventory)
    return (len(missing) == 0, missing)


def subtract_ingredients(
    inventory: list[InventoryItem], recipe: Recipe
) -> list[InventoryItem]:
    required: dict[tuple[str, str], float] = defaultdict(float)
    for ing in recipe.ingredients:
        required[(_normalize(ing.name), _normalize(ing.unit))] += ing.quantity

    updated: list[InventoryItem] = []
    for item in inventory:
        key = (_normalize(item.name), _normalize(item.unit))
        needed = required.get(key, 0)
        if needed <= 0:
            updated.append(item)
            continue

        deduction = min(item.quantity, needed)
        required[key] -= deduction
        remaining = item.quantity - deduction
        if remaining > 0:
            updated.append(item.model_copy(update={"quantity": round(remaining, 2)}))
    return updated


def get_low_stock_items(
    inventory: list[InventoryItem], thresholds: dict[str, float]
) -> list[InventoryItem]:
    threshold_n = {_normalize(name): qty for name, qty in thresholds.items()}
    return [
        item
        for item in inventory
        if item.quantity < threshold_n.get(_normalize(item.name), float("inf"))
    ]


def rank_recipes_for_user(
    recipes: list[Recipe], user: UserProfile, inventory: list[InventoryItem]
) -> list[Recipe]:
    expiry_items = sort_by_expiry_priority([i for i in inventory if i.expiry_date is not None])
    expiry_rank = {item.name: max(1, 100 - idx * 5) for idx, item in enumerate(expiry_items)}
    cuisine_pref = {_normalize(c) for c in user.preferred_cuisines}

    def time_fit_score(recipe: Recipe) -> int:
        if user.time_available == TimeAvailability.QUICK:
            return 10 if recipe.cook_time_minutes <= 30 else 0
        if user.time_available == TimeAvailability.NORMAL:
            return 10 if recipe.cook_time_minutes <= 60 else 3
        return 10

    def score(recipe: Recipe) -> int:
        expiry_score = sum(expiry_rank.get(ing.name, 0) for ing in recipe.ingredients)
        rating_score = 20 if "favorite" in {_normalize(tag) for tag in recipe.tags} else 0
        cuisine_score = 10 if _normalize(recipe.cuisine) in cuisine_pref else 0
        return expiry_score * 10 + rating_score * 5 + cuisine_score * 2 + time_fit_score(recipe)

    return sorted(recipes, key=score, reverse=True)
