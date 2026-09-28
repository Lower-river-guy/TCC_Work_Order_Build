"""Load default (GCS), uploaded, or no template for a work-order operation."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.builder import extract_template_zip, validate_work_order_template_root
from app.gcs_template import fetch_master_template_bytes
from app.settings import max_upload_bytes

TEMPLATE_SOURCE_DEFAULT = "default"
TEMPLATE_SOURCE_UPLOAD = "upload"
TEMPLATE_SOURCE_NONE = "none"


@dataclass(frozen=True)
class TemplateSelection:
    label: str
    kind: str
    filename: str | None = None


def normalize_template_source(raw: object) -> str:
    value = str(raw or "").strip().lower()
    if value in {TEMPLATE_SOURCE_DEFAULT, "true", "default_template"}:
        return TEMPLATE_SOURCE_DEFAULT
    if value in {TEMPLATE_SOURCE_UPLOAD, "upload", "custom", "custom_zip"}:
        return TEMPLATE_SOURCE_UPLOAD
    if value in {TEMPLATE_SOURCE_NONE, "none", "no_template", "custom_only"}:
        return TEMPLATE_SOURCE_NONE
    if value in {"false", "0"}:
        return TEMPLATE_SOURCE_UPLOAD
    raise ValueError("Select a template source: Default Template, Upload Custom ZIP, or No Template.")


def resolve_template_selection(
    source: str,
    custom_bytes: bytes | None,
    custom_filename: str | None,
) -> tuple[bytes | None, TemplateSelection]:
    if source == TEMPLATE_SOURCE_DEFAULT:
        return fetch_master_template_bytes(), TemplateSelection(label="Default", kind="default")

    if source == TEMPLATE_SOURCE_UPLOAD:
        if custom_bytes is None or not custom_filename:
            raise ValueError("Upload Custom Work Order Template (.zip).")
        validate_custom_template_bytes(custom_bytes, custom_filename)
        safe_name = Path(custom_filename).name
        return custom_bytes, TemplateSelection(
            label=f"Uploaded — {safe_name}",
            kind="upload",
            filename=safe_name,
        )

    if source == TEMPLATE_SOURCE_NONE:
        return None, TemplateSelection(
            label="No Template — Custom Work Orders Only",
            kind="none",
        )

    raise ValueError("Select a template source: Default Template, Upload Custom ZIP, or No Template.")


def validate_custom_template_bytes(zip_bytes: bytes, filename: str | None) -> None:
    if not filename or not filename.lower().endswith(".zip"):
        raise ValueError("Custom template must be a .zip file.")
    if not zip_bytes:
        raise ValueError("The uploaded ZIP is empty.")
    if len(zip_bytes) > max_upload_bytes():
        raise ValueError("Upload exceeds the configured size limit.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as error:
        raise ValueError("The uploaded file is not a valid ZIP archive.") from error
    with archive:
        _ = archive.namelist()


def prepare_template_root(zip_bytes: bytes, work_root: Path) -> Path:
    """Extract a validated template ZIP into a unique directory under work_root."""
    template_dir = work_root / "template-in"
    template_dir.mkdir(parents=True, exist_ok=True)
    input_root = extract_template_zip(zip_bytes, template_dir)
    validate_work_order_template_root(input_root)
    return input_root
