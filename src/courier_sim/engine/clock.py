"""Timezone-aware simulation clock helpers."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

BUCHAREST = ZoneInfo("Europe/Bucharest")


class ClockError(ValueError):
    """Simulation time was asked to move in an invalid direction."""


@dataclass(frozen=True)
class SimulationClock:
    """A clock controlled only by explicit simulation commands."""

    current: datetime

    def __post_init__(self) -> None:
        if self.current.tzinfo is None or self.current.utcoffset() is None:
            raise ClockError("simulation datetime must be timezone-aware")
        object.__setattr__(self, "current", as_bucharest_datetime(self.current))

    def advance_by(self, amount: timedelta) -> datetime:
        if amount <= timedelta(0):
            raise ClockError("time advance must be greater than zero")
        # Duration controls represent elapsed simulation time. UTC arithmetic makes the
        # result identical before and after JSON reloads and across daylight-saving changes.
        return (self.current.astimezone(UTC) + amount).astimezone(BUCHAREST)

    def advance_to(self, target: datetime, *, allow_equal: bool = False) -> datetime:
        target = as_bucharest_datetime(target)
        if target < self.current or (target == self.current and not allow_equal):
            raise ClockError(
                f"simulation time cannot move from {format_datetime(self.current)} "
                f"to {format_datetime(target)}"
            )
        return target


def as_bucharest_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=BUCHAREST)
    return value.astimezone(BUCHAREST)


def parse_cli_datetime(value: str) -> datetime:
    """Parse ISO-like CLI input, treating a missing offset as Europe/Bucharest."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ClockError("datetime must use ISO format, for example '2026-03-16 17:00'") from exc
    return as_bucharest_datetime(parsed)


def format_datetime(value: datetime) -> str:
    localized = as_bucharest_datetime(value)
    return f"{localized:%Y-%m-%d %H:%M} Europe/Bucharest"
