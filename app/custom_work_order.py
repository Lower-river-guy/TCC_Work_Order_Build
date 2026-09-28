"""Comma-separated custom work orders added outside (or instead of) a template."""

from __future__ import annotations

import re
from pathlib import Path

from app.settings import OUTPUT_SUBFOLDER_NAME, PLACEHOLDER_DATA

_UNSAFE = re.compile(r'[\\/:*?"<>|]')
_CONTROL = re.compile(r"[\x00-\x1f]")


def validate_custom_base_name(raw: str) -> str:
    """Validate one comma-separated base name (prefix not included)."""
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValueError("Work order name cannot be blank.")
    if cleaned in {".", ".."} or ".." in cleaned:
        raise ValueError(f'Invalid work order name "{cleaned}": path characters are not allowed.')
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError(f'Invalid work order name "{cleaned}": must not contain path separators.')
    if _CONTROL.search(cleaned):
        raise ValueError(f'Invalid work order name "{cleaned}": control characters are not allowed.')
    if _UNSAFE.search(cleaned):
        raise ValueError(f'Invalid work order name "{cleaned}": invalid filename characters.')
    if len(cleaned) > 200:
        raise ValueError(f'Invalid work order name "{cleaned}": must be 200 characters or fewer.')
    return cleaned


def resolve_custom_work_order_folder(prefix: str, raw_name: str) -> str:
    """Build the final folder name, avoiding a duplicated prefix."""
    cleaned = validate_custom_base_name(raw_name)
    body = cleaned
    if body.lower().startswith(prefix.lower()):
        body = body[len(prefix) :].strip()
        if not body:
            raise ValueError(f'Invalid work order name "{raw_name}": enter a name after the prefix.')
        validate_custom_base_name(body)
    folder = f"{prefix}{body}"
    if ".." in folder or "/" in folder or "\\" in folder:
        raise ValueError(f'Invalid work order name "{raw_name}": path characters are not allowed.')
    return folder


def parse_comma_separated_base_names(raw: str) -> list[str]:
    """Split, trim, and drop empty comma-separated entries."""
    if not (raw or "").strip():
        return []
    names: list[str] = []
    for part in raw.split(","):
        cleaned = part.strip()
        if cleaned:
            names.append(cleaned)
    return names


def resolve_custom_work_order_folders(prefix: str, raw: str) -> list[str]:
    """Parse comma-separated names and return unique final folder names."""
    bases = parse_comma_separated_base_names(raw)
    folders: list[str] = []
    seen: set[str] = set()
    for base in bases:
        folder = resolve_custom_work_order_folder(prefix, base)
        key = folder.lower()
        if key in seen:
            raise ValueError(f'Duplicate work order name: {folder}')
        seen.add(key)
        folders.append(folder)
    return folders


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


def add_custom_work_orders_to_staging(staging: Path, prefix: str, raw_names: str) -> list[str]:
    """Materialize all custom work orders. Returns folder names requested (materialized or skipped)."""
    folders = resolve_custom_work_order_folders(prefix, raw_names)
    for folder in folders:
        materialize_custom_work_order(staging, folder)
    return folders
