"""Build a TCC work-order ZIP from a template folder.

Folder names are renamed, each non-Output folder receives a placeholder file
and an Output folder, and existing files are copied into the archive.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.settings import (
    MAX_UNCOMPRESSED_BYTES,
    MAX_UPLOAD_FILES,
    OUTPUT_SUBFOLDER_NAME,
    PLACEHOLDER_DATA,
)


@dataclass
class BuildReport:
    work_orders: list[str] = field(default_factory=list)
    existing_files: int = 0
    placeholder_files: int = 0
    output_folders: int = 0
    directory_entries: int = 0
    skipped_files: int = 0
    log: list[str] = field(default_factory=list)


def ci_replace(text: str, pattern: str, replacement: str) -> str:
    """Replace a literal string without regard to case."""
    if not pattern:
        return text
    return re.sub(
        re.escape(pattern),
        lambda _match: replacement,
        text,
        flags=re.IGNORECASE,
    )


def transform_folder_name(folder_name: str, search: str, replacement: str) -> str:
    """Rename a folder. A folder named Output stays exactly Output."""
    if folder_name.lower() == OUTPUT_SUBFOLDER_NAME.lower():
        return OUTPUT_SUBFOLDER_NAME
    return ci_replace(folder_name, search, replacement)


def transform_path_parts(relative_path: Path, search: str, replacement: str) -> Path:
    """Rename every folder component. Output stays Output."""
    if relative_path == Path("."):
        return Path(".")
    renamed_parts = [
        transform_folder_name(part, search, replacement) for part in relative_path.parts
    ]
    return Path(*renamed_parts)


def join_archive(top_name: str, relative_path: Path) -> Path:
    """Join archive parts without leaving a trailing dot component."""
    if relative_path == Path("."):
        return Path(top_name)
    return Path(top_name) / relative_path


def write_directory_entry(zip_file: zipfile.ZipFile, archive_directory: Path) -> None:
    """Add an explicit directory entry to the ZIP file."""
    archive_name = archive_directory.as_posix().rstrip("/") + "/"
    try:
        zip_file.getinfo(archive_name)
    except KeyError:
        zip_file.writestr(archive_name, b"")


def write_placeholder_file(zip_file: zipfile.ZipFile, archive_file: Path) -> bool:
    """Add the small placeholder file when that name is not already present."""
    archive_name = archive_file.as_posix()
    try:
        zip_file.getinfo(archive_name)
        return False
    except KeyError:
        zip_file.writestr(
            archive_name,
            PLACEHOLDER_DATA.encode("utf-8"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        return True


def make_unique_top_name(requested_name: str, used_names: set[str]) -> str:
    """Prevent duplicate top-level folder names in the ZIP."""
    candidate = requested_name
    counter = 2
    while candidate.lower() in used_names:
        candidate = f"{requested_name}_{counter}"
        counter += 1
    used_names.add(candidate.lower())
    return candidate


def existing_placeholder_name(source_directory: Path) -> str | None:
    """Return a file whose name matches its parent folder, if one exists."""
    parent_name = source_directory.name.lower()
    try:
        for item in source_directory.iterdir():
            if item.is_file() and item.name.lower() == parent_name:
                return item.name
    except OSError:
        return None
    return None


def _safe_zip_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ValueError(f"Unsafe path in upload: {name}")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"Unsafe path in upload: {name}")
    return "/".join(parts)


def extract_template_zip(zip_bytes: bytes, dest: Path) -> Path:
    """Extract an uploaded template ZIP and return the work-order root."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_UPLOAD_FILES:
            raise ValueError("Upload contains too many files.")
        uncompressed = sum(info.file_size for info in infos)
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("Upload expands to more data than this app accepts.")

        for info in infos:
            safe_name = _safe_zip_name(info.filename)
            if not safe_name:
                continue
            target = dest / safe_name
            if info.is_dir() or info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                output.write(source.read())

    entries = [path for path in dest.iterdir() if path.name not in {"__MACOSX", ".DS_Store"}]
    directories = [path for path in entries if path.is_dir()]
    files = [path for path in entries if path.is_file()]
    # A ZIP of the template folder itself has one wrapper directory whose
    # children are the work orders. A single work order that already contains
    # files stays as that folder.
    if len(directories) == 1 and not files:
        inner = directories[0]
        inner_entries = [path for path in inner.iterdir() if path.name != ".DS_Store"]
        inner_files = [path for path in inner_entries if path.is_file()]
        inner_dirs = [path for path in inner_entries if path.is_dir()]
        if inner_dirs and not inner_files:
            return inner
    return dest


def validate_work_order_template_root(input_root: Path) -> None:
    """Require at least one top-level work-order folder after extraction."""
    if not input_root.exists() or not input_root.is_dir():
        raise ValueError("Invalid work order template structure.")
    folders = [
        path
        for path in input_root.iterdir()
        if path.is_dir() and path.name not in {"__MACOSX", ".DS_Store"}
    ]
    if not folders:
        raise ValueError("Invalid work order template: no work-order folders were found.")


def build_work_orders(input_root: Path, search: str, replacement: str) -> tuple[bytes, BuildReport]:
    """Create the work-order ZIP described by REV09."""
    report = BuildReport()
    if not input_root.exists() or not input_root.is_dir():
        raise ValueError(f"Input folder was not found: {input_root}")

    source_folders = sorted(
        (path for path in input_root.iterdir() if path.is_dir() and path.name != "__MACOSX"),
        key=lambda path: path.name.lower(),
    )
    if not source_folders:
        raise ValueError("No work-order folders were found in the uploaded template.")

    report.log.append(f"[FOLDER RENAME] {search} -> {replacement}")
    report.log.append(f"[WORK ORDERS] {len(source_folders)}")

    used_top_names: set[str] = set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as zip_file:
        for source_folder in source_folders:
            requested_top_name = transform_folder_name(
                source_folder.name,
                search,
                replacement,
            )
            renamed_top = make_unique_top_name(requested_top_name, used_top_names)
            report.work_orders.append(renamed_top)
            report.log.append(f"[SOURCE FOLDER] {source_folder.name}")
            report.log.append(f"[ZIP FOLDER] {renamed_top}")

            relative_directories: set[Path] = {Path(".")}
            for root, directories, _files in os.walk(source_folder):
                relative_root = Path(root).relative_to(source_folder)
                relative_directories.add(relative_root)
                for directory_name in directories:
                    relative_directories.add(relative_root / directory_name)

            for relative_directory in sorted(
                relative_directories,
                key=lambda path: (len(path.parts), path.as_posix().lower()),
            ):
                renamed_relative = transform_path_parts(relative_directory, search, replacement)
                archive_directory = join_archive(renamed_top, renamed_relative)
                write_directory_entry(zip_file, archive_directory)
                report.directory_entries += 1
                report.log.append(f"[FOLDER] {archive_directory.as_posix()}")

                if archive_directory.name.lower() == OUTPUT_SUBFOLDER_NAME.lower():
                    continue

                source_directory = (
                    source_folder if relative_directory == Path(".") else source_folder / relative_directory
                )
                existing_name = existing_placeholder_name(source_directory)
                if existing_name is None:
                    placeholder_file = archive_directory / archive_directory.name
                    if write_placeholder_file(zip_file, placeholder_file):
                        report.placeholder_files += 1
                        report.log.append(
                            f"[PLACEHOLDER] {placeholder_file.as_posix()} contains "
                            f"'{PLACEHOLDER_DATA.strip()}'"
                        )
                else:
                    report.log.append(f"[EXISTING PLACEHOLDER] {existing_name}")

                required_output = archive_directory / OUTPUT_SUBFOLDER_NAME
                write_directory_entry(zip_file, required_output)
                report.output_folders += 1
                report.log.append(f"[OUTPUT FOLDER] {required_output.as_posix()}")

            for root, _directories, filenames in os.walk(source_folder):
                root_path = Path(root)
                relative_directory = root_path.relative_to(source_folder)
                renamed_relative = transform_path_parts(relative_directory, search, replacement)
                archive_directory = join_archive(renamed_top, renamed_relative)
                for filename in sorted(filenames, key=str.lower):
                    source_file = root_path / filename
                    if filename.lower() == root_path.name.lower():
                        archive_filename = archive_directory.name
                    else:
                        archive_filename = filename
                    archive_file = archive_directory / archive_filename
                    try:
                        zip_file.write(source_file, archive_file.as_posix())
                        report.existing_files += 1
                        report.log.append(f"[FILE] {archive_file.as_posix()}")
                    except Exception as error:
                        report.skipped_files += 1
                        report.log.append(
                            f"[SKIPPED] {source_file} {type(error).__name__}: {error}"
                        )

    return buffer.getvalue(), report
