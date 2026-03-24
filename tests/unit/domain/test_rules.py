
from __future__ import annotations

from datetime import date
from uuid import uuid4

from apron.domain.enums import CookingSkill, IngredientSource, TimeAvailability
from apron.domain.models import InventoryItem, Recipe, RecipeIngredient, UserProfile
from apron.domain.rules import (
    calculate_missing_ingredients,
    can_cook_now,
    contains_allergen,
    filter_safe_recipes,
    get_low_stock_items,
    is_within_budget,
    rank_recipes_for_user,
    sort_by_expiry_priority,
    subtract_ingredients,
)


def _recipe(name: str, ingredients: list[tuple[str, float, str]], cook_time: int = 30, tags: list[str] | None = None) -> Recipe:
    return Recipe(
        id=uuid4(),
        name=name,
        description=f"{name} description",
        cuisine="mediterranean",
        cook_time_minutes=cook_time,
        difficulty=CookingSkill.INTERMEDIATE,
        servings=2,
        ingredients=[RecipeIngredient(name=i[0], quantity=i[1], unit=i[2]) for i in ingredients],
        steps=["step 1"],
        image_url=None,
        tags=tags or [],
    )


def test_contains_allergen_exact_case_insensitive(sample_recipe):
    sample_recipe = sample_recipe.model_copy(
        update={"ingredients": [RecipeIngredient(name="Peanut", quantity=1, unit="units")]}
    )
    assert contains_allergen(sample_recipe, ["peanut"])


def test_contains_allergen_partial_match(sample_recipe):
    sample_recipe = sample_recipe.model_copy(
        update={"ingredients": [RecipeIngredient(name="peanut butter", quantity=10, unit="g")]}
    )
    assert contains_allergen(sample_recipe, ["peanut"])


def test_contains_allergen_no_match(sample_recipe):
    assert not contains_allergen(sample_recipe, ["shellfish"])


def test_filter_safe_recipes_removes_allergens_and_disliked(sample_user):
    allergen_recipe = _recipe("Allergen", [("peanut", 1, "units")])
    disliked_recipe = _recipe("Disliked", [("anchovy", 50, "g")])
    safe_recipe = _recipe("Safe", [("rice", 200, "g")])
    user = sample_user.model_copy(update={"allergies": ["peanut"], "disliked_ingredients": ["anchovy"]})

    safe = filter_safe_recipes([allergen_recipe, disliked_recipe, safe_recipe], user)
    assert [r.name for r in safe] == ["Safe"]


def test_sort_by_expiry_priority_none_last(sample_user, fake_clock):
    first = InventoryItem(
        id=uuid4(), user_id=sample_user.id, name="milk", quantity=1, unit="l",
        expiry_date=date(2025, 7, 15), date_added=fake_clock.now(), source=IngredientSource.MANUAL
    )
    second = InventoryItem(
        id=uuid4(), user_id=sample_user.id, name="yogurt", quantity=1, unit="units",
        expiry_date=date(2025, 7, 14), date_added=fake_clock.now(), source=IngredientSource.MANUAL
    )
    none_expiry = InventoryItem(
        id=uuid4(), user_id=sample_user.id, name="salt", quantity=1, unit="g",
        expiry_date=None, date_added=fake_clock.now(), source=IngredientSource.MANUAL
    )

    sorted_items = sort_by_expiry_priority([first, none_expiry, second])
    assert [i.name for i in sorted_items] == ["yogurt", "milk", "salt"]


def test_calculate_missing_ingredients_some_missing(sample_recipe, sample_inventory):
    missing = calculate_missing_ingredients([sample_recipe], sample_inventory)
    assert missing == []

    too_big = sample_recipe.model_copy(
        update={
            "ingredients": [
                RecipeIngredient(name="chicken", quantity=900, unit="g"),
                RecipeIngredient(name="rice", quantity=200, unit="g"),
            ]
        }
    )
    missing = calculate_missing_ingredients([too_big], sample_inventory)
    assert len(missing) == 1
    assert missing[0].name == "chicken"
    assert missing[0].quantity == 400


def test_subtract_ingredients_exact_partial_and_exhausted(sample_recipe, sample_inventory):
    updated = subtract_ingredients(sample_inventory, sample_recipe)
    by_name = {i.name: i for i in updated}
    assert by_name["chicken"].quantity == 200
    assert by_name["rice"].quantity == 200

    exhaustive = _recipe("Big Chicken", [("chicken", 999, "g")])
    updated2 = subtract_ingredients(sample_inventory, exhaustive)
    assert all(item.name != "chicken" for item in updated2)


def test_is_within_budget_under_exact_over():
    assert is_within_budget(10.0, 20.0)
    assert is_within_budget(20.0, 20.0)
    assert not is_within_budget(20.01, 20.0)


def test_can_cook_now_all_and_missing(sample_recipe, sample_inventory):
    ok, missing = can_cook_now(sample_recipe, sample_inventory)
    assert ok is True
    assert missing == []

    impossible = sample_recipe.model_copy(
        update={"ingredients": [RecipeIngredient(name="saffron", quantity=5, unit="g")]}
    )
    ok2, missing2 = can_cook_now(impossible, sample_inventory)
    assert ok2 is False
    assert missing2[0].name == "saffron"


def test_get_low_stock_items(sample_user, fake_clock):
    items = [
        InventoryItem(
            id=uuid4(), user_id=sample_user.id, name="rice", quantity=100, unit="g",
            expiry_date=None, date_added=fake_clock.now(), source=IngredientSource.MANUAL
        ),
        InventoryItem(
            id=uuid4(), user_id=sample_user.id, name="olive oil", quantity=500, unit="ml",
            expiry_date=None, date_added=fake_clock.now(), source=IngredientSource.MANUAL
        ),
    ]
    low = get_low_stock_items(items, {"rice": 200, "olive oil": 250})
    assert [i.name for i in low] == ["rice"]


def test_rank_recipes_expiry_then_preference(sample_user, sample_inventory):
    user = sample_user.model_copy(
        update={
            "preferred_cuisines": ["mediterranean"],
            "time_available": TimeAvailability.QUICK,
        }
    )

    recipe_uses_expiry = _recipe("Expiry", [("chicken", 300, "g")], cook_time=25)
    favorite_slow = _recipe("Favorite", [("rice", 200, "g")], cook_time=75, tags=["favorite"])
    unrelated = _recipe("Unrelated", [("beef", 300, "g")], cook_time=20)

    ranked = rank_recipes_for_user([unrelated, favorite_slow, recipe_uses_expiry], user, sample_inventory)
    assert ranked[0].name == "Expiry"
