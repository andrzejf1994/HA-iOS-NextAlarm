"""Lightweight voluptuous stand-in for tests."""

from __future__ import annotations

from typing import Any, Iterable


class Schema:
    """Store the provided schema definition without enforcing validation."""

    def __init__(self, schema: Any) -> None:
        self.schema = schema

    def __call__(self, data: Any) -> Any:
        return data


class _Marker(str):
    """Simple marker object carrying a default value attribute."""

    def __new__(cls, value: str, default: Any | None = None) -> "_Marker":
        obj = str.__new__(cls, value)
        obj.default = default
        return obj


def Required(value: str, default: Any | None = None) -> _Marker:
    return _Marker(value, default)


def Optional(value: str, default: Any | None = None) -> _Marker:
    return _Marker(value, default)


class In:
    """Minimal validator placeholder."""

    def __init__(self, options: Iterable[Any]) -> None:
        self.options = list(options)

    def __contains__(self, value: Any) -> bool:
        return value in self.options

    def __call__(self, value: Any) -> Any:
        if value not in self.options:
            raise ValueError(f"{value!r} not in options")
        return value
