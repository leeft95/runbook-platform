"""Service-owned schedule evaluation."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter  # type: ignore[import-untyped]


def latest_due_slot(expression: str, timezone_name: str, now: datetime) -> datetime:
    """Return the latest UTC cron slot at or before an aware instant."""
    if now.tzinfo is None:
        raise ValueError("schedule evaluation requires a timezone-aware datetime")
    current = now.astimezone(ZoneInfo(timezone_name))
    if croniter.match(expression, current):
        return current.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return croniter(expression, current).get_prev(datetime).astimezone(timezone.utc).replace(second=0, microsecond=0)
