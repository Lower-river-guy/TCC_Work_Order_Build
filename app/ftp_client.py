"""TCC FTP listing and work-order upload.

Login credentials come from the environment. The web UI chooses the device
and project. Existing remote work orders are left in place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from ftplib import FTP, error_perm
from pathlib import Path

from app.settings import (
    DEFAULT_FTP_HOST,
    DEFAULT_FTP_PORT,
    DEFAULT_FTP_TIMEOUT,
    REMOTE_DEVICES_ROOT,
    REMOTE_PROJECTS_CONTAINER,
    REMOTE_WORK_ORDERS_FOLDER,
    STAGING_FOLDER_NAME,
)


@dataclass
class UploadReport:
    dry_run: bool
    device: str
    project: str
    target: str
    directories: int = 0
    files: int = 0
    skipped_existing_work_orders: int = 0
    log: list[str] = field(default_factory=list)


def load_env_file(path: Path) -> dict[str, str]:
    """Load a simple KEY=VALUE file."""
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
    """Find the T48 username and password using the master-env key names."""
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
    """Return whether an FTP login can be resolved. Never returns the secret."""
    try:
        username, password = resolve_credentials()
    except Exception:
        return False
    return bool(username and password)


def resolve_credentials() -> tuple[str, str]:
    """Resolve T48 FTP credentials from the environment or an optional env file."""
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
    """Open an FTP session. The password is not included in raised errors."""
    host = os.environ.get("TCC_FTP_HOST", DEFAULT_FTP_HOST).strip() or DEFAULT_FTP_HOST
    port = int(os.environ.get("TCC_FTP_PORT", str(DEFAULT_FTP_PORT)))
    timeout = int(os.environ.get("TCC_FTP_TIMEOUT", str(DEFAULT_FTP_TIMEOUT)))
    username, password = resolve_credentials()
    ftp = FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(username, password)
    ftp.set_pasv(True)
    return ftp


def ftp_list_directories(ftp: FTP) -> list[str]:
    """Return directory names in the current FTP directory."""
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
    """Reject path tricks before a remote folder name is used."""
    cleaned = (name or "").strip()
    if not cleaned or cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
        raise RuntimeError("Choose a folder name from the list.")
    return cleaned


def require_child_directory(ftp: FTP, requested_name: str) -> str:
    """Return the server's exact directory name after checking the listing."""
    requested = validate_remote_name(requested_name)
    existing = {name.lower(): name for name in ftp_list_directories(ftp)}
    match = existing.get(requested.lower())
    if match is None:
        raise RuntimeError(f"Folder was not found: {requested}")
    return match


def ftp_ensure_dir(ftp: FTP, folder_name: str, dry_run: bool, log: list[str]) -> bool:
    """Enter folder_name, creating it only when this is not a dry run."""
    existing = {name.lower(): name for name in ftp_list_directories(ftp)}
    match = existing.get(folder_name.lower())
    if match:
        ftp.cwd(match)
        return True
    if dry_run:
        log.append(f"[DRY RUN - WOULD CREATE] {ftp.pwd().rstrip('/')}/{folder_name}")
        return False
    ftp.mkd(folder_name)
    ftp.cwd(folder_name)
    log.append(f"[FTP CREATED] {ftp.pwd()}")
    return True


def count_local_directory_contents(local_root: Path) -> tuple[int, int]:
    """Count files and subdirectories for dry-run reporting."""
    files = 0
    directories = 0
    for item in local_root.rglob("*"):
        if item.is_dir():
            directories += 1
        elif item.is_file():
            files += 1
    return files, directories


def upload_new_directory_contents(ftp: FTP, local_root: Path, log: list[str]) -> tuple[int, int]:
    """Recursively upload a work-order directory that did not already exist."""
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


def upload_tree(ftp: FTP, local_root: Path, dry_run: bool, log: list[str]) -> tuple[int, int, int]:
    """Upload new top-level work orders and skip names that already exist."""
    uploaded = 0
    directories = 0
    skipped_work_orders = 0
    remote_dirs = {name.lower(): name for name in ftp_list_directories(ftp)}

    for item in sorted(local_root.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
        if item.is_dir():
            if item.name.lower() in remote_dirs:
                skipped_work_orders += 1
                log.append(f"[SKIP EXISTING WORK ORDER] {item.name}")
                continue
            if dry_run:
                directories += 1
                log.append(f"[DRY RUN - WOULD UPLOAD WORK ORDER] {item.name}")
                sub_uploaded, sub_dirs = count_local_directory_contents(item)
                uploaded += sub_uploaded
                directories += sub_dirs
            else:
                ftp.mkd(item.name)
                ftp.cwd(item.name)
                directories += 1
                log.append(f"[NEW WORK ORDER] {item.name}")
                sub_uploaded, sub_dirs = upload_new_directory_contents(ftp, item, log)
                uploaded += sub_uploaded
                directories += sub_dirs
                ftp.cwd("..")
        elif item.is_file():
            remote_names = {name.rstrip("/").split("/")[-1].lower() for name in ftp.nlst()}
            if item.name.lower() in remote_names:
                log.append(f"[SKIP EXISTING FILE] {item.name}")
                continue
            if dry_run:
                uploaded += 1
                log.append(f"[DRY RUN - WOULD UPLOAD FILE] {item.name}")
            else:
                with item.open("rb") as handle:
                    ftp.storbinary(f"STOR {item.name}", handle)
                uploaded += 1
                log.append(f"[FTP FILE] {item.name}")
    return uploaded, directories, skipped_work_orders


def stage_work_orders(zip_bytes: bytes, output_root: Path) -> Path:
    """Extract the generated ZIP into a clean Work Orders staging folder."""
    import io
    import shutil
    import zipfile

    staging = output_root / STAGING_FOLDER_NAME
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        archive.extractall(staging)
    return staging


def list_devices(ftp: FTP) -> list[str]:
    """List device folders under the TCC synchronizer root."""
    try:
        ftp.cwd(REMOTE_DEVICES_ROOT)
    except error_perm as error:
        raise RuntimeError(f"Could not enter device root {REMOTE_DEVICES_ROOT}: {error}") from error
    return ftp_list_directories(ftp)


def list_projects(ftp: FTP, device: str) -> list[str]:
    """List project folders for one device."""
    list_devices(ftp)
    device_name = require_child_directory(ftp, device)
    ftp.cwd(device_name)
    container = require_child_directory(ftp, REMOTE_PROJECTS_CONTAINER)
    ftp.cwd(container)
    return ftp_list_directories(ftp)


def upload_work_orders(ftp: FTP, staging: Path, device: str, project: str, dry_run: bool) -> UploadReport:
    """Upload staging into the selected device and project."""
    log: list[str] = []
    try:
        ftp.cwd(REMOTE_DEVICES_ROOT)
    except error_perm as error:
        raise RuntimeError(f"Could not enter device root {REMOTE_DEVICES_ROOT}: {error}") from error

    device_name = require_child_directory(ftp, device)
    ftp.cwd(device_name)
    device_path = ftp.pwd()
    log.append(f"[DEVICE] {device_name}")

    projects_container = require_child_directory(ftp, REMOTE_PROJECTS_CONTAINER)
    ftp.cwd(projects_container)
    expected_project_root = f"{device_path.rstrip('/')}/{projects_container}"
    actual_project_root = ftp.pwd()
    if actual_project_root.rstrip("/").lower() != expected_project_root.rstrip("/").lower():
        raise RuntimeError(
            "Project-root verification failed. "
            f"Expected {expected_project_root}, got {actual_project_root}."
        )
    log.append(f"[PROJECT ROOT] {actual_project_root}")

    project_name = require_child_directory(ftp, project)
    ftp.cwd(project_name)
    log.append(f"[PROJECT] {project_name}")

    before = ftp.pwd()
    entered = ftp_ensure_dir(ftp, REMOTE_WORK_ORDERS_FOLDER, dry_run, log)
    if entered:
        target = ftp.pwd()
        uploaded, directories, skipped = upload_tree(ftp, staging, dry_run, log)
    else:
        target = f"{before.rstrip('/')}/{REMOTE_WORK_ORDERS_FOLDER}"
        uploaded = 0
        directories = 0
        skipped = 0
        for item in sorted(staging.iterdir(), key=lambda path: path.name.lower()):
            if item.is_dir():
                log.append(f"[DRY RUN - WOULD UPLOAD WORK ORDER] {item.name}")
                directories += 1
                file_count, directory_count = count_local_directory_contents(item)
                uploaded += file_count
                directories += directory_count

    log.append("[DRY RUN COMPLETE]" if dry_run else "[FTP COMPLETE]")
    log.append(f"[DIRECTORIES] {directories}")
    log.append(f"[FILES] {uploaded}")
    log.append(f"[SKIPPED EXISTING WORK ORDERS] {skipped}")
    log.append(f"[TARGET] {target}")
    if dry_run:
        log.append("[CHANGES MADE] NONE")

    return UploadReport(
        dry_run=dry_run,
        device=device_name,
        project=project_name,
        target=target,
        directories=directories,
        files=uploaded,
        skipped_existing_work_orders=skipped,
        log=log,
    )
