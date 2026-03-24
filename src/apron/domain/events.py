from pydantic import BaseModel, ConfigDict
from uuid import UUID

from apron.domain.models import InventoryItem, MealPlan, Order, PlannedMeal


class InventoryLow(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    items: list[InventoryItem]


class MealCooked(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    planned_meal: PlannedMeal


class MealSkipped(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    planned_meal: PlannedMeal


class MealPlanConfirmed(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    meal_plan: MealPlan


class OrderPlaced(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    order: Order
