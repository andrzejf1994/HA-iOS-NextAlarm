"""Minimal ConfigEntry implementation for tests."""

from __future__ import annotations

from typing import Any, Callable


class ConfigEntry:
    """Simple config entry stub."""

    def __init__(
        self,
        *,
        entry_id: str = "test-entry",
        domain: str = "",
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.domain = domain
        self.data = data or {}
        self.options = options or {}
        self._unload_callbacks: list[Callable[[], None]] = []

    def add_update_listener(self, listener: Callable[[Any, "ConfigEntry"], Any]) -> Callable[[], None]:
        """Register a listener and return a remover."""

        def remove() -> None:
            if remove in self._unload_callbacks:
                self._unload_callbacks.remove(remove)

        self._unload_callbacks.append(remove)
        return remove

    def async_on_unload(self, callback: Callable[[], None]) -> None:
        """Register a callback to invoke on unload."""

        self._unload_callbacks.append(callback)

    async def async_unload(self) -> None:
        """Invoke unload callbacks."""

        for callback in list(self._unload_callbacks):
            callback()


class ConfigEntries:
    """Placeholder for hass.config_entries."""

    async def async_forward_entry_setups(self, entry: ConfigEntry, platforms: list[str]) -> None:
        return None

    async def async_unload_platforms(self, entry: ConfigEntry, platforms: list[str]) -> bool:
        return True

    async def async_reload(self, entry_id: str) -> None:
        return None
