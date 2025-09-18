"""Minimal data entry flow helpers for tests."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict

FlowResult = Dict[str, Any]


class FlowResultType(str, Enum):
    """Mirror of Home Assistant's flow result types."""

    FORM = "form"
    CREATE_ENTRY = "create_entry"
    ABORT = "abort"


class AbortFlow(Exception):
    """Exception raised when a flow is aborted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
