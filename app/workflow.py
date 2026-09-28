"""Build work orders from a template source and compare or upload on TCC FTP."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.builder import build_work_orders
from app.ftp_client import (
    compare_work_orders,
    connect_ftp,
    navigate_to_work_orders,
    stage_work_orders,
    upload_work_orders,
)
from app.ftp_guard import ReadOnlyFTP
from app.prefix import validate_prefix
from app.settings import MASTER_TEMPLATE_SEARCH
from app.template_source import TemplateSelection, load_template_zip_bytes, prepare_template_root


@dataclass(frozen=True)
class OperationRequest:
    prefix: str
    device: str
    project: str
    use_default_template: bool
    custom_bytes: bytes | None = None
    custom_filename: str | None = None


def build_staging(request: OperationRequest, work_root: Path) -> tuple[Path, list[str], str, TemplateSelection]:
    validated_prefix = validate_prefix(request.prefix)
    zip_bytes, template = load_template_zip_bytes(
        use_default=request.use_default_template,
        custom_bytes=request.custom_bytes,
        custom_filename=request.custom_filename,
    )
    input_root = prepare_template_root(zip_bytes, work_root)
    built_zip, report = build_work_orders(input_root, MASTER_TEMPLATE_SEARCH, validated_prefix)
    staging = stage_work_orders(built_zip, work_root)
    return staging, list(report.work_orders), validated_prefix, template


def preview_on_tcc(request: OperationRequest):
    with tempfile.TemporaryDirectory(prefix="tcc-wo-") as temp_name:
        work_root = Path(temp_name)
        staging, _names, prefix, template = build_staging(request, work_root)
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
            )
        finally:
            _close(ftp)


def run_on_tcc(request: OperationRequest, *, dry_run: bool, confirm_upload: bool):
    if not dry_run and not confirm_upload:
        raise ValueError("Confirm upload is required before making changes on TCC.")

    with tempfile.TemporaryDirectory(prefix="tcc-wo-") as temp_name:
        work_root = Path(temp_name)
        staging, _names, prefix, template = build_staging(request, work_root)
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
