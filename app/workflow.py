"""Build work orders from the GCS master template and compare or upload on TCC FTP."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.builder import build_work_orders, extract_template_zip
from app.ftp_client import (
    compare_work_orders,
    connect_ftp,
    navigate_to_work_orders,
    stage_work_orders,
    upload_work_orders,
)
from app.ftp_guard import ReadOnlyFTP
from app.gcs_template import fetch_master_template_bytes
from app.grade_checkers import GradeChecker, get_grade_checker


def build_staging_from_master(grade_checker_id: str, work_root: Path) -> tuple[Path, list[str], GradeChecker]:
    checker = get_grade_checker(grade_checker_id)
    zip_bytes = fetch_master_template_bytes()
    template_dir = work_root / "template"
    template_dir.mkdir(parents=True, exist_ok=True)
    input_root = extract_template_zip(zip_bytes, template_dir)
    built_zip, report = build_work_orders(input_root, checker.search, checker.replace)
    staging = stage_work_orders(built_zip, work_root)
    return staging, list(report.work_orders), checker


def preview_on_tcc(grade_checker_id: str, device: str, project: str):
    with tempfile.TemporaryDirectory(prefix="tcc-wo-") as temp_name:
        work_root = Path(temp_name)
        staging, _names, checker = build_staging_from_master(grade_checker_id, work_root)
        ftp = connect_ftp()
        try:
            guarded = ReadOnlyFTP(ftp, read_only=True)
            device_name, project_name, target, inside = navigate_to_work_orders(
                guarded, device, project, dry_run=True
            )
            return compare_work_orders(
                guarded,
                staging,
                device_name,
                project_name,
                target,
                checker,
                inside,
            )
        finally:
            _close(ftp)


def run_on_tcc(
    grade_checker_id: str,
    device: str,
    project: str,
    *,
    dry_run: bool,
    confirm_upload: bool,
):
    if not dry_run and not confirm_upload:
        raise ValueError("Confirm upload is required before making changes on TCC.")

    with tempfile.TemporaryDirectory(prefix="tcc-wo-") as temp_name:
        work_root = Path(temp_name)
        staging, _names, checker = build_staging_from_master(grade_checker_id, work_root)
        ftp = connect_ftp()
        try:
            if dry_run:
                guarded = ReadOnlyFTP(ftp, read_only=True)
                device_name, project_name, target, inside = navigate_to_work_orders(
                    guarded, device, project, dry_run=True
                )
                return compare_work_orders(
                    guarded,
                    staging,
                    device_name,
                    project_name,
                    target,
                    checker,
                    inside,
                )
            device_name, project_name, _target, _inside = navigate_to_work_orders(
                ftp, device, project, dry_run=False
            )
            return upload_work_orders(ftp, staging, checker, device_name, project_name)
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
