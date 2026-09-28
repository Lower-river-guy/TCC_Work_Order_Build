"""TCC FTP listing, preview comparison, and work-order upload."""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from ftplib import FTP, error_perm
from pathlib import Path
from typing import TYPE_CHECKING

from app.settings import (
    DEFAULT_FTP_HOST,
    DEFAULT_FTP_PORT,
    DEFAULT_FTP_TIMEOUT,
    DRY_RUN_BANNER,
    REMOTE_DEVICES_ROOT,
    REMOTE_PROJECTS_CONTAINER,
    REMOTE_WORK_ORDERS_FOLDER,
    STAGING_FOLDER_NAME,
)

if TYPE_CHECKING:
    from app.grade_checkers import GradeChecker


@dataclass
class WorkOrderRow:
    work_order: str
    status: str
    action: str

    def as_dict(self) -> dict[str, str]:
        return {
            "work_order": self.work_order,
            "status": self.status,
            "action": self.action,
        }


@dataclass
class UploadReport:
    dry_run: bool
    grade_checker: str
    prefix: str
    device: str
    project: str
    target: str
    banner: str = ""
    totals: dict[str, int] = field(default_factory=dict)
    rows: list[WorkOrderRow] = field(default_factory=list)
    directories: int = 0
    files: int = 0
    skipped_existing_work_orders: int = 0
    log: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "grade_checker": self.grade_checker,
            "prefix": self.prefix,
            "device": self.device,
            "project": self.project,
            "target": self.target,
            "banner": self.banner,
            "totals": dict(self.totals),
            "rows": [row.as_dict() for row in self.rows],
            "directories": self.directories,
            "files": self.files,
            "skipped_existing_work_orders": self.skipped_existing_work_orders,
            "log": list(self.log),
        }


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Device env file not found: {path}")
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_t48_credentials(values: dict[str, str]) -> tuple[str, str]:
    upper = {key.upper(): value for key, value in values.items()}
    user_keys = [
        "TCC_T48_DEVICE_USER",
        "T48_USER",
        "T48_USERNAME",
        "T48_FTP_USER",
        "T48_FTP_USERNAME",
        "T48_USER_NAME",
    ]
    pass_keys = [
        "TCC_T48_DEVICE_PASS",
        "T48_PASS",
        "T48_PASSWORD",
        "T48_FTP_PASS",
        "T48_FTP_PASSWORD",
    ]
    username = next((upper[key] for key in user_keys if upper.get(key)), None)
    password = next((upper[key] for key in pass_keys if upper.get(key)), None)
    if not username:
        username = next((value for key, value in upper.items() if "T48" in key and "USER" in key), None)
    if not password:
        password = next(
            (value for key, value in upper.items() if "T48" in key and ("PASS" in key or "PWD" in key)),
            None,
        )
    if not username or not password:
        available = ", ".join(sorted(key for key in values if "T48" in key.upper())) or "none"
        raise RuntimeError(
            "Could not identify the T48 username/password. "
            f"T48-related keys found: {available}"
        )
    return username, password


def credentials_configured() -> bool:
    try:
        username, password = resolve_credentials()
    except Exception:
        return False
    return bool(username and password)


def resolve_credentials() -> tuple[str, str]:
    username = os.environ.get("TCC_T48_DEVICE_USER", "").strip()
    password = os.environ.get("TCC_T48_DEVICE_PASS", "").strip()
    if username and password:
        return username, password
    env_file = os.environ.get("TCC_DEVICE_ENV_FILE", "").strip()
    if env_file:
        return get_t48_credentials(load_env_file(Path(env_file)))
    raise RuntimeError(
        "TCC FTP credentials are not configured. "
        "Set TCC_T48_DEVICE_USER and TCC_T48_DEVICE_PASS."
    )


def connect_ftp() -> FTP:
    host = os.environ.get("TCC_FTP_HOST", DEFAULT_FTP_HOST).strip() or DEFAULT_FTP_HOST
    port = int(os.environ.get("TCC_FTP_PORT", str(DEFAULT_FTP_PORT)))
    timeout = int(os.environ.get("TCC_FTP_TIMEOUT", str(DEFAULT_FTP_TIMEOUT)))
    username, password = resolve_credentials()
    ftp = FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(username, password)
    ftp.set_pasv(True)
    return ftp


def ftp_list_directories(ftp) -> list[str]:
    directories: list[str] = []
    try:
        for name, facts in ftp.mlsd():
            if name not in (".", "..") and facts.get("type") == "dir":
                directories.append(name)
        return sorted(directories, key=str.lower)
    except Exception:
        pass
    original = ftp.pwd()
    for name in ftp.nlst():
        clean = name.rstrip("/").split("/")[-1]
        if clean in ("", ".", ".."):
            continue
        try:
            ftp.cwd(clean)
            directories.append(clean)
            ftp.cwd(original)
        except error_perm:
            try:
                ftp.cwd(original)
            except Exception:
                pass
    return sorted(set(directories), key=str.lower)


def validate_remote_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned or cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
        raise RuntimeError("Choose a folder name from the list.")
    return cleaned


def require_child_directory(ftp, requested_name: str) -> str:
    requested = validate_remote_name(requested_name)
    existing = {name.lower(): name for name in ftp_list_directories(ftp)}
    match = existing.get(requested.lower())
    if match is None:
        raise RuntimeError(f"Folder was not found: {requested}")
    return match


def list_devices(ftp) -> list[str]:
    try:
        ftp.cwd(REMOTE_DEVICES_ROOT)
    except error_perm as error:
        raise RuntimeError(f"Could not enter device root {REMOTE_DEVICES_ROOT}: {error}") from error
    return ftp_list_directories(ftp)


def list_projects(ftp, device: str) -> list[str]:
    list_devices(ftp)
    device_name = require_child_directory(ftp, device)
    ftp.cwd(device_name)
    container = require_child_directory(ftp, REMOTE_PROJECTS_CONTAINER)
    ftp.cwd(container)
    return ftp_list_directories(ftp)


def navigate_to_work_orders(
    ftp, device: str, project: str, dry_run: bool
) -> tuple[str, str, str, bool]:
    """Walk REV09 path to the project's Work Orders folder. Creates Work Orders only when not dry run."""
    log: list[str] = []
    try:
        ftp.cwd(REMOTE_DEVICES_ROOT)
    except error_perm as error:
        raise RuntimeError(f"Could not enter device root {REMOTE_DEVICES_ROOT}: {error}") from error

    device_name = require_child_directory(ftp, device)
    ftp.cwd(device_name)
    device_path = ftp.pwd()

    projects_container = require_child_directory(ftp, REMOTE_PROJECTS_CONTAINER)
    ftp.cwd(projects_container)
    expected_project_root = f"{device_path.rstrip('/')}/{projects_container}"
    actual_project_root = ftp.pwd()
    if actual_project_root.rstrip("/").lower() != expected_project_root.rstrip("/").lower():
        raise RuntimeError(
            "Project-root verification failed. "
            f"Expected {expected_project_root}, got {actual_project_root}."
        )

    project_name = require_child_directory(ftp, project)
    ftp.cwd(project_name)
    before = ftp.pwd()

    entered = _enter_work_orders_folder(ftp, dry_run, log)
    if entered:
        target = ftp.pwd()
    else:
        target = f"{before.rstrip('/')}/{REMOTE_WORK_ORDERS_FOLDER}"
    return device_name, project_name, target, entered


def _enter_work_orders_folder(ftp, dry_run: bool, log: list[str]) -> bool:
    existing = {name.lower(): name for name in ftp_list_directories(ftp)}
    match = existing.get(REMOTE_WORK_ORDERS_FOLDER.lower())
    if match:
        ftp.cwd(match)
        return True
    if dry_run:
        log.append(f"[DRY RUN - WOULD CREATE] {ftp.pwd().rstrip('/')}/{REMOTE_WORK_ORDERS_FOLDER}")
        return False
    ftp.mkd(REMOTE_WORK_ORDERS_FOLDER)
    ftp.cwd(REMOTE_WORK_ORDERS_FOLDER)
    log.append(f"[FTP CREATED] {ftp.pwd()}")
    return True


def _plan_rows(staging: Path, remote_names: set[str], dry_run: bool) -> tuple[list[WorkOrderRow], dict[str, int]]:
    rows: list[WorkOrderRow] = []
    new_count = 0
    existing_count = 0
    for item in sorted(staging.iterdir(), key=lambda path: path.name.lower()):
        if not item.is_dir():
            continue
        if item.name.lower() in remote_names:
            rows.append(WorkOrderRow(item.name, "Exists", "Skip"))
            existing_count += 1
        else:
            action = "Would Upload" if dry_run else "Upload"
            rows.append(WorkOrderRow(item.name, "New", action))
            new_count += 1
    totals = {
        "total": len(rows),
        "new": new_count,
        "existing": existing_count,
    }
    return rows, totals


def compare_work_orders(
    ftp,
    staging: Path,
    device_name: str,
    project_name: str,
    target: str,
    checker: GradeChecker,
    inside_work_orders: bool,
) -> UploadReport:
    remote_names: set[str] = set()
    if inside_work_orders:
        remote_names = {name.lower() for name in ftp_list_directories(ftp)}

    rows, totals = _plan_rows(staging, remote_names, dry_run=True)
    uploaded = 0
    directories = 0
    for item in staging.iterdir():
        if item.is_dir() and item.name.lower() not in remote_names:
            directories += 1
            file_count, dir_count = count_local_directory_contents(item)
            uploaded += file_count
            directories += dir_count

    log = [
        DRY_RUN_BANNER,
        f"[GRADE CHECKER] {checker.label}",
        f"[PREFIX] {checker.prefix}",
        f"[DEVICE] {device_name}",
        f"[PROJECT] {project_name}",
        f"[TARGET] {target}",
    ]
    return UploadReport(
        dry_run=True,
        grade_checker=checker.label,
        prefix=checker.prefix,
        device=device_name,
        project=project_name,
        target=target,
        banner=DRY_RUN_BANNER,
        totals=totals,
        rows=rows,
        directories=directories,
        files=uploaded,
        skipped_existing_work_orders=totals["existing"],
        log=log,
    )


def count_local_directory_contents(local_root: Path) -> tuple[int, int]:
    files = 0
    directories = 0
    for item in local_root.rglob("*"):
        if item.is_dir():
            directories += 1
        elif item.is_file():
            files += 1
    return files, directories


def upload_new_directory_contents(ftp, local_root: Path, log: list[str]) -> tuple[int, int]:
    uploaded = 0
    directories = 0
    for item in sorted(local_root.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
        if item.is_dir():
            ftp.mkd(item.name)
            ftp.cwd(item.name)
            directories += 1
            sub_uploaded, sub_dirs = upload_new_directory_contents(ftp, item, log)
            uploaded += sub_uploaded
            directories += sub_dirs
            ftp.cwd("..")
        elif item.is_file():
            with item.open("rb") as handle:
                ftp.storbinary(f"STOR {item.name}", handle)
            uploaded += 1
            log.append(f"[FTP FILE] {item.name}")
    return uploaded, directories


def upload_tree(ftp, local_root: Path, log: list[str]) -> tuple[int, int, int, list[WorkOrderRow]]:
    uploaded = 0
    directories = 0
    skipped_work_orders = 0
    rows: list[WorkOrderRow] = []

    for item in sorted(local_root.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
        if not item.is_dir():
            continue
        remote_dirs = {name.lower(): name for name in ftp_list_directories(ftp)}
        if item.name.lower() in remote_dirs:
            skipped_work_orders += 1
            rows.append(WorkOrderRow(item.name, "Exists", "Skip"))
            log.append(f"[SKIP EXISTING WORK ORDER] {item.name}")
            continue
        remote_dirs = {name.lower(): name for name in ftp_list_directories(ftp)}
        if item.name.lower() in remote_dirs:
            skipped_work_orders += 1
            rows.append(WorkOrderRow(item.name, "Exists", "Skip — Already Exists"))
            log.append(f"[SKIP — ALREADY EXISTS] {item.name}")
            continue
        ftp.mkd(item.name)
        ftp.cwd(item.name)
        directories += 1
        rows.append(WorkOrderRow(item.name, "New", "Upload"))
        log.append(f"[NEW WORK ORDER] {item.name}")
        sub_uploaded, sub_dirs = upload_new_directory_contents(ftp, item, log)
        uploaded += sub_uploaded
        directories += sub_dirs
        ftp.cwd("..")

    return uploaded, directories, skipped_work_orders, rows


def stage_work_orders(zip_bytes: bytes, output_root: Path) -> Path:
    staging = output_root / STAGING_FOLDER_NAME
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        archive.extractall(staging)
    return staging


def upload_work_orders(
    ftp,
    staging: Path,
    checker: GradeChecker,
    device_name: str,
    project_name: str,
) -> UploadReport:
    """Upload new work orders. FTP must already be inside the project's Work Orders folder."""
    uploaded, directories, skipped, rows = upload_tree(ftp, staging, log := [])
    log.insert(0, f"[PREFIX] {checker.prefix}")
    log.insert(0, f"[GRADE CHECKER] {checker.label}")
    totals = {
        "total": len(rows),
        "new": sum(1 for row in rows if row.status == "New"),
        "existing": sum(1 for row in rows if row.status == "Exists"),
    }
    return UploadReport(
        dry_run=False,
        grade_checker=checker.label,
        prefix=checker.prefix,
        device=device_name,
        project=project_name,
        target=ftp.pwd(),
        banner="",
        totals=totals,
        rows=rows,
        directories=directories,
        files=uploaded,
        skipped_existing_work_orders=skipped,
        log=log,
    )
