from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID

import aiosqlite

from apron.domain.enums import (
    ConversationState,
    CookingSkill,
    IngredientSource,
    TimeAvailability,
)
from apron.domain.models import InventoryItem, UserProfile

_USERS_DDL = """\
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,
    household_size INTEGER DEFAULT 2,
    allergies TEXT DEFAULT '[]',
    dietary_preferences TEXT DEFAULT '[]',
    taste_profiles TEXT DEFAULT '[]',
    weekly_budget REAL DEFAULT 100.0,
    preferred_cuisines TEXT DEFAULT '[]',
    cooking_skill TEXT DEFAULT 'intermediate',
    time_available TEXT DEFAULT 'normal',
    disliked_ingredients TEXT DEFAULT '[]',
    conversation_state TEXT DEFAULT 'onboarding',
    onboarding_step INTEGER DEFAULT 0,
    mercadona_email TEXT DEFAULT '',
    mercadona_password TEXT DEFAULT '',
    telegram_chat_id TEXT DEFAULT '',
    created_at TEXT,
    updated_at TEXT
)"""

_INVENTORY_DDL = """\
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    expiry_date TEXT,
    date_added TEXT,
    source TEXT NOT NULL
)"""


class SqliteUserRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute(_USERS_DDL)
            await self._conn.commit()
        return self._conn

    async def get_by_phone(self, phone: str) -> UserProfile | None:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM users WHERE phone_number = ?", (phone,)
        ) as cur:
            row = await cur.fetchone()
        return self._map(row) if row else None

    async def get_by_id(self, user_id: UUID) -> UserProfile:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM users WHERE id = ?", (str(user_id),)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise ValueError("User not found")
        return self._map(row)

    async def save(self, user: UserProfile) -> UserProfile:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT INTO users (
                id, phone_number, household_size, allergies, dietary_preferences,
                taste_profiles, weekly_budget, preferred_cuisines, cooking_skill,
                time_available, disliked_ingredients, conversation_state,
                onboarding_step, mercadona_email, mercadona_password, telegram_chat_id,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            self._to_row(user),
        )
        await conn.commit()
        return user

    async def update(self, user: UserProfile) -> UserProfile:
        conn = await self._get_conn()
        await conn.execute(
            """UPDATE users SET
                household_size=?, allergies=?, dietary_preferences=?,
                taste_profiles=?, weekly_budget=?, preferred_cuisines=?,
                cooking_skill=?, time_available=?, disliked_ingredients=?,
                conversation_state=?, onboarding_step=?,
                mercadona_email=?, mercadona_password=?, telegram_chat_id=?,
                updated_at=?
            WHERE id=?""",
            (
                user.household_size,
                json.dumps(user.allergies),
                json.dumps(user.dietary_preferences),
                json.dumps(user.taste_profiles),
                user.weekly_budget,
                json.dumps(user.preferred_cuisines),
                user.cooking_skill.value,
                user.time_available.value,
                json.dumps(user.disliked_ingredients),
                user.conversation_state.value,
                user.onboarding_step,
                user.mercadona_email,
                user.mercadona_password,
                user.telegram_chat_id,
                user.updated_at.isoformat(),
                str(user.id),
            ),
        )
        await conn.commit()
        return user

    @staticmethod
    def _to_row(u: UserProfile) -> tuple:
        return (
            str(u.id),
            u.phone_number,
            u.household_size,
            json.dumps(u.allergies),
            json.dumps(u.dietary_preferences),
            json.dumps(u.taste_profiles),
            u.weekly_budget,
            json.dumps(u.preferred_cuisines),
            u.cooking_skill.value,
            u.time_available.value,
            json.dumps(u.disliked_ingredients),
            u.conversation_state.value,
            u.onboarding_step,
            u.mercadona_email,
            u.mercadona_password,
            u.telegram_chat_id,
            u.created_at.isoformat(),
            u.updated_at.isoformat(),
        )

    async def delete(self, user_id: UUID) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM users WHERE id = ?", (str(user_id),))
        await conn.commit()

    async def list_all(self) -> list[UserProfile]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [self._map(row) for row in rows]

    @staticmethod
    def _map(row) -> UserProfile:
        return UserProfile(
            id=UUID(row["id"]),
            phone_number=row["phone_number"],
            household_size=row["household_size"],
            allergies=json.loads(row["allergies"]),
            dietary_preferences=json.loads(row["dietary_preferences"]),
            taste_profiles=json.loads(row["taste_profiles"]),
            weekly_budget=float(row["weekly_budget"]),
            preferred_cuisines=json.loads(row["preferred_cuisines"]),
            cooking_skill=CookingSkill(row["cooking_skill"]),
            time_available=TimeAvailability(row["time_available"]),
            disliked_ingredients=json.loads(row["disliked_ingredients"]),
            conversation_state=ConversationState(row["conversation_state"]),
            onboarding_step=row["onboarding_step"],
            mercadona_email=row["mercadona_email"] or "",
            mercadona_password=row["mercadona_password"] or "",
            telegram_chat_id=row["telegram_chat_id"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class SqliteInventoryRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute(_INVENTORY_DDL)
            await self._conn.commit()
        return self._conn

    async def get_all(self, user_id: UUID) -> list[InventoryItem]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT * FROM inventory WHERE user_id = ?", (str(user_id),)
        ) as cur:
            rows = await cur.fetchall()
        return [self._map(r) for r in rows]

    async def upsert(self, item: InventoryItem) -> InventoryItem:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO inventory
                (id, user_id, name, quantity, unit, expiry_date, date_added, source)
            VALUES (?,?,?,?,?,?,?,?)""",
            self._to_row(item),
        )
        await conn.commit()
        return item

    async def bulk_upsert(self, items: list[InventoryItem]) -> list[InventoryItem]:
        conn = await self._get_conn()
        await conn.executemany(
            """INSERT OR REPLACE INTO inventory
                (id, user_id, name, quantity, unit, expiry_date, date_added, source)
            VALUES (?,?,?,?,?,?,?,?)""",
            [self._to_row(i) for i in items],
        )
        await conn.commit()
        return items

    async def delete(self, item_id: UUID) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM inventory WHERE id = ?", (str(item_id),))
        await conn.commit()

    @staticmethod
    def _to_row(i: InventoryItem) -> tuple:
        return (
            str(i.id),
            str(i.user_id),
            i.name,
            i.quantity,
            i.unit,
            i.expiry_date.isoformat() if i.expiry_date else None,
            i.date_added.isoformat(),
            i.source.value,
        )

    @staticmethod
    def _map(row) -> InventoryItem:
        return InventoryItem(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            name=row["name"],
            quantity=float(row["quantity"]),
            unit=row["unit"],
            expiry_date=date.fromisoformat(row["expiry_date"]) if row["expiry_date"] else None,
            date_added=datetime.fromisoformat(row["date_added"]),
            source=IngredientSource(row["source"]),
        )
