"""Optional single work order added outside the template ZIP."""

from __future__ import annotations

import re
from pathlib import Path

from app.settings import OUTPUT_SUBFOLDER_NAME, PLACEHOLDER_DATA

_UNSAFE = re.compile(r'[\\/:*?"<>|]')
_CONTROL = re.compile(r"[\x00-\x1f]")


def validate_custom_work_order_name(raw: str) -> str:
    """Validate the user-entered work order name (suffix or prefixed)."""
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValueError("Enter a work order name.")
    if cleaned in {".", ".."} or ".." in cleaned:
        raise ValueError("Work order name contains invalid path characters.")
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError("Work order name must not contain path separators.")
    if _CONTROL.search(cleaned):
        raise ValueError("Work order name contains invalid control characters.")
    if _UNSAFE.search(cleaned):
        raise ValueError("Work order name contains invalid characters.")
    if len(cleaned) > 200:
        raise ValueError("Work order name must be 200 characters or fewer.")
    return cleaned


def resolve_custom_work_order_folder(prefix: str, raw_name: str) -> str:
    """Build the final FTP folder name, avoiding a duplicated prefix."""
    cleaned = validate_custom_work_order_name(raw_name)
    body = cleaned
    if body.lower().startswith(prefix.lower()):
        body = body[len(prefix) :].strip()
        if not body:
            raise ValueError("Enter a work order name.")
        validate_custom_work_order_name(body)
    folder = f"{prefix}{body}"
    if ".." in folder or "/" in folder or "\\" in folder:
        raise ValueError("Work order name contains invalid path characters.")
    return folder


def materialize_custom_work_order(staging: Path, folder_name: str) -> bool:
    """Write WorksManager placeholder layout under staging. Returns False if folder exists."""
    work_order_dir = staging / folder_name
    if work_order_dir.exists():
        return False
    work_order_dir.mkdir(parents=True, exist_ok=True)
    placeholder = work_order_dir / folder_name
    placeholder.write_bytes(PLACEHOLDER_DATA.encode("utf-8"))
    (work_order_dir / OUTPUT_SUBFOLDER_NAME).mkdir()
    return True


def add_custom_work_order_to_staging(
    staging: Path,
    prefix: str,
    *,
    enabled: bool,
    raw_name: str | None,
) -> str | None:
    """Optionally add one custom work order folder to the staging tree."""
    if not enabled:
        return None
    folder_name = resolve_custom_work_order_folder(prefix, raw_name or "")
    materialize_custom_work_order(staging, folder_name)
    return folder_name
