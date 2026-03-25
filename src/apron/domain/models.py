from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apron.domain.enums import (
    ConversationState,
    CookingSkill,
    IngredientSource,
    MealType,
    OrderStatus,
    TimeAvailability,
)


class UserProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    phone_number: str
    household_size: int = 2
    allergies: list[str] = Field(default_factory=list)
    dietary_preferences: list[str] = Field(default_factory=list)
    taste_profiles: list[str] = Field(default_factory=list)
    weekly_budget: float = 100.0
    preferred_cuisines: list[str] = Field(default_factory=list)
    cooking_skill: CookingSkill = CookingSkill.INTERMEDIATE
    time_available: TimeAvailability = TimeAvailability.NORMAL
    disliked_ingredients: list[str] = Field(default_factory=list)
    conversation_state: ConversationState = ConversationState.ONBOARDING
    onboarding_step: int = 0
    mercadona_email: str = ""
    mercadona_password: str = ""
    telegram_chat_id: str = ""
    created_at: datetime
    updated_at: datetime


class InventoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID
    name: str
    quantity: float
    unit: str
    expiry_date: date | None
    date_added: datetime
    source: IngredientSource


class RecipeIngredient(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    quantity: float
    unit: str


class Recipe(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    description: str
    cuisine: str
    cook_time_minutes: int
    difficulty: CookingSkill
    servings: int
    ingredients: list[RecipeIngredient]
    steps: list[str]
    image_url: str | None
    tags: list[str] = Field(default_factory=list)


class PlannedMeal(BaseModel):
    model_config = ConfigDict(frozen=True)

    day: date
    meal_type: MealType
    recipe: Recipe
    skipped: bool = False
    cooked: bool = False
    rating: int | None = None


class MealPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID
    week_start: date
    meals: list[PlannedMeal]
    total_estimated_cost: float
    missing_ingredients: list[RecipeIngredient]
    confirmed: bool = False
    created_at: datetime


class OrderItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    quantity: float
    unit: str
    price: float


class Order(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID
    items: list[OrderItem]
    source: str
    status: OrderStatus
    total_price: float
    estimated_delivery_minutes: int | None
    created_at: datetime


class ShoppingListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID
    name: str
    quantity: float
    unit: str
    added_by: str
    purchased: bool = False
