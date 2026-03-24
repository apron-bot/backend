
from __future__ import annotations


class ProactiveSchedulerService:
    def __init__(self, user_repo, inventory_service, planner_service):
        self._user_repo = user_repo
        self._inventory_service = inventory_service
        self._planner_service = planner_service

    async def sunday_meal_plan(self, user_id=None) -> None:
        if user_id:
            await self._planner_service.generate_weekly_plan(user_id)
            return

    async def daily_reminder(self, user_id=None) -> None:
        if user_id:
            await self._planner_service.send_daily_reminder(user_id)
            return

    async def low_stock_check(self, user_id=None) -> None:
        if user_id:
            await self._inventory_service.check_low_stock(user_id)
            return
