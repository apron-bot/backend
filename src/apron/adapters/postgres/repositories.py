
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg

from apron.domain.models import InventoryItem, UserProfile


class PostgresUserRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_by_phone(self, phone: str) -> UserProfile | None:
        row = await self._pool.fetchrow("SELECT * FROM users WHERE phone_number = $1", phone)
        return self._map_user(row) if row else None

    async def get_by_id(self, user_id: UUID) -> UserProfile:
        row = await self._pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        if not row:
            raise ValueError("User not found")
        return self._map_user(row)

    async def save(self, user: UserProfile) -> UserProfile:
        await self._pool.execute(
            """
            INSERT INTO users (
                id, phone_number, household_size, allergies, dietary_preferences,
                taste_profiles, weekly_budget, preferred_cuisines, cooking_skill,
                time_available, disliked_ingredients, conversation_state,
                onboarding_step, created_at, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15
            )
            """,
            user.id,
            user.phone_number,
            user.household_size,
            user.allergies,
            user.dietary_preferences,
            user.taste_profiles,
            Decimal(str(user.weekly_budget)),
            user.preferred_cuisines,
            user.cooking_skill.value,
            user.time_available.value,
            user.disliked_ingredients,
            user.conversation_state.value,
            user.onboarding_step,
            user.created_at,
            user.updated_at,
        )
        return user

    async def update(self, user: UserProfile) -> UserProfile:
        await self._pool.execute(
            """
            UPDATE users SET
                household_size=$2,
                allergies=$3,
                dietary_preferences=$4,
                taste_profiles=$5,
                weekly_budget=$6,
                preferred_cuisines=$7,
                cooking_skill=$8,
                time_available=$9,
                disliked_ingredients=$10,
                conversation_state=$11,
                onboarding_step=$12,
                updated_at=$13
            WHERE id=$1
            """,
            user.id,
            user.household_size,
            user.allergies,
            user.dietary_preferences,
            user.taste_profiles,
            Decimal(str(user.weekly_budget)),
            user.preferred_cuisines,
            user.cooking_skill.value,
            user.time_available.value,
            user.disliked_ingredients,
            user.conversation_state.value,
            user.onboarding_step,
            user.updated_at,
        )
        return user

    @staticmethod
    def _map_user(row) -> UserProfile:
        return UserProfile(
            id=row["id"],
            phone_number=row["phone_number"],
            household_size=row["household_size"],
            allergies=row["allergies"],
            dietary_preferences=row["dietary_preferences"],
            taste_profiles=row["taste_profiles"],
            weekly_budget=float(row["weekly_budget"]),
            preferred_cuisines=row["preferred_cuisines"],
            cooking_skill=row["cooking_skill"],
            time_available=row["time_available"],
            disliked_ingredients=row["disliked_ingredients"],
            conversation_state=row["conversation_state"],
            onboarding_step=row["onboarding_step"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class PostgresInventoryRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_all(self, user_id: UUID) -> list[InventoryItem]:
        rows = await self._pool.fetch("SELECT * FROM inventory WHERE user_id = $1", user_id)
        return [
            InventoryItem(
                id=r["id"],
                user_id=r["user_id"],
                name=r["name"],
                quantity=float(r["quantity"]),
                unit=r["unit"],
                expiry_date=r["expiry_date"],
                date_added=r["date_added"],
                source=r["source"],
            )
            for r in rows
        ]
