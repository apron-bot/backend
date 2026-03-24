from datetime import date, datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        return date.today()


class FakeClock:
    def __init__(self, frozen: datetime):
        self._frozen = frozen

    def now(self) -> datetime:
        return self._frozen

    def today(self) -> date:
        return self._frozen.date()
