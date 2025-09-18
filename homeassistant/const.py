"""Home Assistant constants for tests."""

from __future__ import annotations

from enum import Enum

EVENT_TIME_CHANGED = "time_changed"


class Platform(str, Enum):
    """Supported platforms."""

    SENSOR = "sensor"


class EntityCategory(str, Enum):
    """Entity categories."""

    DIAGNOSTIC = "diagnostic"
