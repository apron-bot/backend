
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apron.api.deps import (
    get_inventory_repo,
    get_order_repo,
    get_plan_repo,
    get_planner,
    get_recipe_repo,
    get_scheduler,
    get_user_repo,
)

router = APIRouter()


class RecipeFilters(BaseModel):
    query: str | None = None


@router.get("/inventory/{user_id}")
async def get_inventory(user_id: UUID, repo=Depends(get_inventory_repo)):
    items = await repo.get_all(user_id)
    return [item.model_dump() for item in items]


@router.get("/meal-plan/{user_id}/current")
async def get_current_plan(user_id: UUID, repo=Depends(get_plan_repo)):
    plan = await repo.get_current(user_id)
    if not plan:
        raise HTTPException(404, "No active meal plan")
    return plan.model_dump()


@router.get("/recipes/{user_id}/favorites")
async def get_favorites(user_id: UUID, repo=Depends(get_recipe_repo)):
    return [r.model_dump() for r in await repo.get_favorites(user_id)]


@router.get("/orders/{user_id}")
async def get_orders(user_id: UUID, repo=Depends(get_order_repo)):
    return [o.model_dump() for o in await repo.get_history(user_id)]


@router.post("/recipes/{user_id}/generate")
async def generate_recipe(user_id: UUID, filters: RecipeFilters, planner=Depends(get_planner)):
    _ = filters
    recipes = await planner.suggest_from_inventory(user_id)
    return [r.model_dump() for r in recipes]


@router.get("/preferences/{user_id}")
async def get_preferences(user_id: UUID, repo=Depends(get_user_repo)):
    user = await repo.get_by_id(user_id)
    return user.model_dump(exclude={"conversation_state", "onboarding_step"})


@router.post("/admin/trigger/meal-plan/{user_id}")
async def trigger_meal_plan(user_id: UUID, scheduler=Depends(get_scheduler)):
    await scheduler.sunday_meal_plan(user_id=user_id)
    return {"ok": True}


@router.post("/admin/trigger/daily-reminder/{user_id}")
async def trigger_daily_reminder(user_id: UUID, scheduler=Depends(get_scheduler)):
    await scheduler.daily_reminder(user_id=user_id)
    return {"ok": True}


@router.post("/admin/trigger/low-stock-check/{user_id}")
async def trigger_low_stock_check(user_id: UUID, scheduler=Depends(get_scheduler)):
    await scheduler.low_stock_check(user_id=user_id)
    return {"ok": True}
