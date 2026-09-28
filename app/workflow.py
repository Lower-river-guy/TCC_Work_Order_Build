"""Build work orders from a template source and compare or upload on TCC FTP."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.builder import build_work_orders
from app.custom_work_order import add_custom_work_orders_to_staging
from app.ftp_client import (
    compare_work_orders,
    connect_ftp,
    navigate_to_work_orders,
    stage_work_orders,
    upload_work_orders,
)
from app.ftp_guard import ReadOnlyFTP
from app.prefix import validate_prefix
from app.settings import MASTER_TEMPLATE_SEARCH, STAGING_FOLDER_NAME
from app.template_source import (
    TEMPLATE_SOURCE_NONE,
    TemplateSelection,
    resolve_template_selection,
    prepare_template_root,
)


@dataclass(frozen=True)
class OperationRequest:
    prefix: str
    device: str
    project: str
    template_source: str
    custom_bytes: bytes | None = None
    custom_filename: str | None = None
    custom_work_order_names: str = ""


def _template_source_label(kind: str) -> str:
    if kind == "upload":
        return "Uploaded Template"
    if kind == "default":
        return "Default"
    return "Custom"


def build_staging(
    request: OperationRequest, work_root: Path
) -> tuple[Path, list[str], str, TemplateSelection, dict[str, str]]:
    validated_prefix = validate_prefix(request.prefix)
    zip_bytes, template = resolve_template_selection(
        request.template_source,
        request.custom_bytes,
        request.custom_filename,
    )

    template_work_orders: list[str] = []
    staging = work_root / STAGING_FOLDER_NAME
    if staging.exists():
        shutil.rmtree(staging)

    if template.kind == TEMPLATE_SOURCE_NONE:
        staging.mkdir(parents=True, exist_ok=True)
    else:
        input_root = prepare_template_root(zip_bytes, work_root)
        built_zip, report = build_work_orders(input_root, MASTER_TEMPLATE_SEARCH, validated_prefix)
        staging = stage_work_orders(built_zip, work_root)
        template_work_orders = list(report.work_orders)

    custom_folders = add_custom_work_orders_to_staging(
        staging, validated_prefix, request.custom_work_order_names
    )

    sources: dict[str, str] = {}
    for name in template_work_orders:
        sources[name] = _template_source_label(template.kind)
    for name in custom_folders:
        if name not in sources and (staging / name).is_dir():
            sources[name] = "Custom"

    work_orders = sorted(
        (path.name for path in staging.iterdir() if path.is_dir()),
        key=str.lower,
    )
    return staging, work_orders, validated_prefix, template, sources


def preview_on_tcc(request: OperationRequest):
    with tempfile.TemporaryDirectory(prefix="tcc-wo-") as temp_name:
        work_root = Path(temp_name)
        staging, _names, prefix, template, sources = build_staging(request, work_root)
        ftp = connect_ftp()
        try:
            guarded = ReadOnlyFTP(ftp, read_only=True)
            device_name, project_name, target, inside = navigate_to_work_orders(
                guarded, request.device, request.project, dry_run=True
            )
            return compare_work_orders(
                guarded,
                staging,
                device_name,
                project_name,
                target,
                prefix,
                template.label,
                inside,
                staging_sources=sources,
            )
        finally:
            _close(ftp)


def run_on_tcc(request: OperationRequest, *, dry_run: bool, confirm_upload: bool):
    if not dry_run and not confirm_upload:
        raise ValueError("Confirm upload is required before making changes on TCC.")

    with tempfile.TemporaryDirectory(prefix="tcc-wo-") as temp_name:
        work_root = Path(temp_name)
        staging, _names, prefix, template, sources = build_staging(request, work_root)
        ftp = connect_ftp()
        try:
            if dry_run:
                guarded = ReadOnlyFTP(ftp, read_only=True)
                device_name, project_name, target, inside = navigate_to_work_orders(
                    guarded, request.device, request.project, dry_run=True
                )
                return compare_work_orders(
                    guarded,
                    staging,
                    device_name,
                    project_name,
                    target,
                    prefix,
                    template.label,
                    inside,
                    staging_sources=sources,
                )
            device_name, project_name, _target, _inside = navigate_to_work_orders(
                ftp, request.device, request.project, dry_run=False
            )
            return upload_work_orders(
                ftp,
                staging,
                prefix,
                template.label,
                device_name,
                project_name,
                staging_sources=sources,
            )
        finally:
            _close(ftp)


def _close(ftp) -> None:
    try:
        ftp.quit()
    except Exception:
        try:
            ftp.close()
        except Exception:
            pass
