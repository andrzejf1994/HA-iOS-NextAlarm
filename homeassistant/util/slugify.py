"""Simple slugify implementation."""

from __future__ import annotations

import re

_slugify_strip_re = re.compile(r"[^\w]+")


def slugify(text: str) -> str:
    text = text or ""
    text = _slugify_strip_re.sub("_", text).strip("_")
    return text.lower()
