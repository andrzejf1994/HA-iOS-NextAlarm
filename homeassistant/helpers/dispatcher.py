"""Simple dispatcher helpers for tests."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..core import HomeAssistant


def async_dispatcher_connect(hass: HomeAssistant, signal: str, target: Callable[..., Any]) -> Callable[[], None]:
    listeners = hass.data.setdefault("_dispatcher", {}).setdefault(signal, [])
    listeners.append(target)

    def remove() -> None:
        if target in listeners:
            listeners.remove(target)

    return remove


def async_dispatcher_send(hass: HomeAssistant, signal: str, *args: Any) -> None:
    for callback in list(hass.data.setdefault("_dispatcher", {}).get(signal, [])):
        result = callback(*args)
        if asyncio.iscoroutine(result):
            hass.loop.create_task(result)
