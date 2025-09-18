"""Datetime helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
DEFAULT_TIME_ZONE = UTC


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    return None


def get_time_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")
