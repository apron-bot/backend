from datetime import date, datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime: ...
    def today(self) -> date: ...
