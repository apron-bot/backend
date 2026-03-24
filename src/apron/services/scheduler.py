
from __future__ import annotations


class ProactiveSchedulerService:
    def __init__(self, user_repo, inventory_service, planner_service):
        self._user_repo = user_repo
        self._inventory_service = inventory_service
        self._planner_service = planner_service

    async def sunday_meal_plan(self) -> None:
        return None

    async def daily_reminder(self) -> None:
        return None

    async def low_stock_check(self) -> None:
        return None
