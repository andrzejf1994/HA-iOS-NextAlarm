"""Event helpers for tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable

from ..const import EVENT_TIME_CHANGED
from ..core import HomeAssistant


def async_track_point_in_time(
    hass: HomeAssistant, action: Callable[[datetime], Any], point_in_time: datetime
) -> Callable[[], None]:
    """Track a moment in time using the time changed event."""

    def _listener(event) -> None:
        now = event.data.get("now")
        if now is None:
            return
        if now >= point_in_time:
            remove()
            result = action(now)
            if asyncio.iscoroutine(result):
                hass.loop.create_task(result)

    remove = hass.bus.async_listen(EVENT_TIME_CHANGED, _listener)
    return remove
