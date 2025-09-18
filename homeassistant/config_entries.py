"""Minimal ConfigEntry and ConfigFlow implementations for tests."""

from __future__ import annotations

from typing import Any, Callable

from .data_entry_flow import FlowResult, FlowResultType


class FlowHandler:
    """Shared helpers for flow handlers."""

    def __init__(self) -> None:
        self.hass = None

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: Any | None = None,
        errors: dict[str, str] | None = None,
    ) -> FlowResult:
        return {
            "type": FlowResultType.FORM,
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }

    def async_abort(self, *, reason: str) -> FlowResult:
        return {"type": FlowResultType.ABORT, "reason": reason}


class ConfigEntry:
    """Simple config entry stub."""

    def __init__(
        self,
        *,
        entry_id: str = "test-entry",
        domain: str = "",
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        unique_id: str | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.domain = domain
        self.data = data or {}
        self.options = options or {}
        self.unique_id = unique_id
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


class ConfigFlow(FlowHandler):
    """Config flow stub mirroring Home Assistant behaviour closely enough for tests."""

    domain: str = ""

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if domain is not None:
            cls.domain = domain

    def __init__(self) -> None:
        super().__init__()
        self.context: dict[str, Any] = {}
        self._unique_id: str | None = None

    async def async_set_unique_id(self, unique_id: str) -> None:
        self._unique_id = unique_id

    def _async_current_entries(self) -> list[ConfigEntry]:
        if self.hass is None:
            return []
        return [
            entry
            for entry in getattr(self.hass.config_entries, "_entries", [])
            if entry.domain == self.domain
        ]

    def _abort_if_unique_id_configured(self) -> FlowResult | None:
        if self._async_current_entries():
            # Return the same structure Home Assistant would generate when a duplicate unique ID is encountered.
            return self.async_abort(reason="already_configured")
        return None

    def async_create_entry(
        self,
        *,
        title: str,
        data: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> FlowResult:
        entry = ConfigEntry(
            domain=self.domain,
            data=data,
            options=options or {},
            unique_id=self._unique_id,
        )
        if self.hass is not None:
            self.hass.config_entries._entries.append(entry)
        return {
            "type": FlowResultType.CREATE_ENTRY,
            "title": title,
            "data": data,
            "options": options or {},
        }


class OptionsFlow(FlowHandler):
    """Options flow stub used by tests."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__()
        self.config_entry = config_entry

    def async_create_entry(self, *, data: dict[str, Any]) -> FlowResult:
        self.config_entry.options = data
        return {"type": FlowResultType.CREATE_ENTRY, "data": data}


class ConfigEntries:
    """Placeholder for hass.config_entries."""

    def __init__(self) -> None:
        self._entries: list[ConfigEntry] = []  # Track entries so unique ID guards can inspect configured items.

    async def async_forward_entry_setups(self, entry: ConfigEntry, platforms: list[str]) -> None:
        return None

    async def async_unload_platforms(self, entry: ConfigEntry, platforms: list[str]) -> bool:
        if entry in self._entries:
            self._entries.remove(entry)
        return True

    async def async_reload(self, entry_id: str) -> None:
        return None
