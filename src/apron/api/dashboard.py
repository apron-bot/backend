
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apron.api.deps import (
    get_inventory_repo,
    get_order_repo,
    get_plan_repo,
    get_planner,
    get_recipe_repo,
    get_scheduler,
    get_settings,
    get_user_repo,
)

router = APIRouter()

# --------------- In-memory stores for demo ---------------
_last_photos: dict[str, str] = {}  # user_id -> base64
_icon_cache: dict[str, str] = {}   # food_name -> base64


def store_photo(user_id: str, image_b64: str):
    _last_photos[user_id] = image_b64


def get_last_photo_b64(user_id: str) -> str | None:
    return _last_photos.get(user_id)


# --------------- Models ---------------

class RecipeFilters(BaseModel):
    query: str | None = None
    servings: int | None = None
    difficulty: str | None = None  # easy, medium, hard
    flavor_profile: dict[str, int] | None = None  # e.g. {"salty": 2, "sweet": 1, ...}


# --------------- User discovery endpoints ---------------

@router.get("/users")
async def list_users(repo=Depends(get_user_repo)):
    """List all users -- for demo/hackathon only."""
    users = await repo.list_all()
    return [
        {
            "id": str(u.id),
            "phone_number": u.phone_number,
            "household_size": u.household_size,
            "conversation_state": u.conversation_state.value if hasattr(u.conversation_state, 'value') else str(u.conversation_state),
            "created_at": str(u.created_at),
        }
        for u in users
    ]


@router.delete("/users/{user_id}")
async def delete_user(user_id: UUID, repo=Depends(get_user_repo)):
    """Delete a user — for demo/hackathon only."""
    try:
        await repo.delete(user_id)
    except Exception:
        pass
    return {"ok": True}


@router.get("/users/by-phone/{phone}")
async def get_user_by_phone(phone: str, repo=Depends(get_user_repo)):
    """Get user by phone/chat_id."""
    user = await repo.get_by_phone(phone)
    if not user:
        raise HTTPException(404, "User not found")
    return {"id": str(user.id), "phone_number": user.phone_number}


# --------------- Photo endpoints ---------------

@router.get("/photos/{user_id}/last")
async def get_last_photo(user_id: str):
    photo = get_last_photo_b64(user_id)
    if not photo:
        raise HTTPException(404, "No photo found")
    return {"image_b64": photo}


# --------------- Icon generation endpoints ---------------

@router.post("/icons/generate")
async def generate_food_icon(request_body: dict):
    """Generate a pixel art food icon using OpenAI DALL-E."""
    food_name = request_body.get("name", "food")

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(500, "OpenAI API key not configured")

    prompt = (
        f"A single {food_name}, cute pixel art, 16-bit retro game style, "
        "soft shading, low detail but expressive, warm lighting, chunky pixels, "
        "clean outlines, slightly cartoonish proportions, vibrant but soft color palette, "
        "cozy atmosphere, high readability, centered composition, transparent background, PNG"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"DALL-E error: {resp.text}")
        data = resp.json()
        image_b64 = data["data"][0]["b64_json"]
        return {"name": food_name, "image_b64": image_b64}


@router.get("/icons/{food_name}")
async def get_food_icon(food_name: str):
    """Get cached food icon, or 404."""
    if food_name.lower() in _icon_cache:
        return {"name": food_name, "image_b64": _icon_cache[food_name.lower()]}
    raise HTTPException(404, "Icon not found, generate it first")


@router.post("/icons/{food_name}/generate")
async def generate_and_cache_icon(food_name: str):
    """Generate and cache a pixel art food icon."""
    if food_name.lower() in _icon_cache:
        return {"name": food_name, "image_b64": _icon_cache[food_name.lower()], "cached": True}

    settings = get_settings()
    if not settings.openai_api_key or settings.openai_api_key.startswith("your_"):
        raise HTTPException(500, "OpenAI API key not configured")

    prompt = (
        f"A single {food_name}, cute pixel art, 16-bit retro game style, "
        "soft shading, low detail but expressive, warm lighting, chunky pixels, "
        "clean outlines, slightly cartoonish proportions, vibrant but soft color palette, "
        "cozy atmosphere, high readability, centered composition, transparent background, "
        "PNG, no text"
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "b64_json",
                },
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, "DALL-E error")
            data = resp.json()
            image_b64 = data["data"][0]["b64_json"]
            _icon_cache[food_name.lower()] = image_b64
            return {"name": food_name, "image_b64": image_b64, "cached": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# --------------- Original endpoints ---------------

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
    # Build a constraint string from filters for the LLM
    parts = []
    if filters.servings:
        parts.append(f"for {filters.servings} people")
    if filters.difficulty:
        parts.append(f"difficulty: {filters.difficulty}")
    if filters.flavor_profile:
        flavors = [f"{k}={v}" for k, v in filters.flavor_profile.items() if v > 0]
        if flavors:
            parts.append(f"flavor emphasis: {', '.join(flavors)}")
    if filters.query:
        parts.append(filters.query)

    constraint = "; ".join(parts) if parts else None
    recipes = await planner.suggest_from_inventory(user_id, constraint=constraint)
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
