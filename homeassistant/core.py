"""Minimal Home Assistant core constructs for tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable

from .config_entries import ConfigEntries
from .const import EVENT_TIME_CHANGED

CALLBACK_TYPE = Callable[[], None]


def callback(func: Callable) -> Callable:
    """Return function unchanged."""

    return func


class EventOrigin(str, Enum):
    """Origin of an event."""

    local = "LOCAL"
    remote = "REMOTE"


@dataclass
class Context:
    """Context information for events."""

    id: str | None = None
    user_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "user_id": self.user_id}


class Event:
    """Representation of an event."""

    def __init__(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        origin: EventOrigin = EventOrigin.local,
        time_fired: datetime | None = None,
        context: Context | None = None,
    ) -> None:
        self.event_type = event_type
        self.data = data or {}
        self.origin = origin
        self.time_fired = time_fired or datetime.utcnow()
        self.context = context or Context()


class EventBus:
    """Simple asynchronous event bus."""

    def __init__(self, hass: "HomeAssistant") -> None:
        self._hass = hass
        self._listeners: dict[str, list[Callable[[Event], Any]]] = {}

    def async_listen(self, event_type: str, listener: Callable[[Event], Any]) -> CALLBACK_TYPE:
        listeners = self._listeners.setdefault(event_type, [])
        listeners.append(listener)

        def remove() -> None:
            if listener in listeners:
                listeners.remove(listener)

        return remove

    def async_fire(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        event = Event(event_type, data)
        for listener in list(self._listeners.get(event_type, [])):
            result = listener(event)
            if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                self._hass.loop.create_task(result)


class HomeAssistant:
    """Simplified Home Assistant instance for tests."""

    def __init__(self) -> None:
        self.loop = asyncio.get_event_loop()
        self.data: dict[str, Any] = {}
        self.config = type("Config", (), {"time_zone": "UTC"})()
        self.bus = EventBus(self)
        self.config_entries = ConfigEntries()

    async def async_block_till_done(self) -> None:
        await asyncio.sleep(0)

    def async_create_task(self, coro: Awaitable[Any]) -> asyncio.Task:
        return self.loop.create_task(coro)
