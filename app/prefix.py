"""Validate user-entered work order prefixes."""

from __future__ import annotations

import re

from app.settings import DEFAULT_PREFIX

_UNSAFE = re.compile(r'[\\/:*?"<>|]')


def validate_prefix(raw: str) -> str:
    """Return a safe prefix or raise ValueError."""
    prefix = (raw or "").strip()
    if not prefix:
        prefix = DEFAULT_PREFIX
    if len(prefix) > 50:
        raise ValueError("Work order prefix must be 50 characters or fewer.")
    if prefix in {".", ".."} or ".." in prefix or "/" in prefix or "\\" in prefix:
        raise ValueError("Work order prefix contains invalid path characters.")
    if _UNSAFE.search(prefix):
        raise ValueError("Work order prefix contains invalid characters.")
    return prefix
