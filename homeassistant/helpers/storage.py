"""Storage helper for tests."""

from __future__ import annotations

from typing import Any

from ..core import HomeAssistant


class Store:
    """Simplified data store using in-memory storage."""

    def __init__(self, hass: HomeAssistant, version: int, key: str) -> None:
        self.hass = hass
        self.version = version
        self.key = key

    async def async_load(self) -> Any:
        return self.hass.data.setdefault("_store", {}).get(self.key)

    async def async_save(self, data: Any) -> None:
        self.hass.data.setdefault("_store", {})[self.key] = data
