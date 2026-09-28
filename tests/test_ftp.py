"""FTP planning tests. These do not open a network connection."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.builder import build_work_orders
from app.ftp_client import (
    compare_work_orders,
    credentials_configured,
    navigate_to_work_orders,
    resolve_credentials,
    stage_work_orders,
    upload_tree,
    upload_work_orders,
    validate_remote_name,
)
from app.ftp_guard import ReadOnlyFTP
from app.settings import DRY_RUN_BANNER, PLACEHOLDER_DATA
from tests.fake_ftp import FakeFTP


def _device_tree(work_orders: dict | None = None) -> dict:
    project: dict = {}
    if work_orders is not None:
        project["Work Orders"] = work_orders
    return {
        "TCC": {
            "sukut": {
                "trimblesynchronizerdata": {
                    "T48": {
                        "Trimble SCS900 Data": {
                            "Project A": project,
                        }
                    }
                }
            }
        }
    }


def _sample_zip(prefix: str = "RK-") -> bytes:
    with tempfile.TemporaryDirectory() as temp_name:
        root = Path(temp_name)
        (root / "DK-New").mkdir()
        (root / "DK-New" / "notes.txt").write_text("notes", encoding="utf-8")
        (root / "DK-Old").mkdir()
        (root / "DK-Old" / "notes.txt").write_text("old", encoding="utf-8")
        payload, _report = build_work_orders(root, "DK-", prefix)
    return payload


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ("TCC_T48_DEVICE_USER", "TCC_T48_DEVICE_PASS")}
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_credentials(self):
        os.environ["TCC_T48_DEVICE_USER"] = "user-only"
        with self.assertRaises(RuntimeError):
            resolve_credentials()
        self.assertFalse(credentials_configured())


class PreviewAndUploadTests(unittest.TestCase):
    def test_dry_run_performs_zero_writes(self):
        ftp = FakeFTP(_device_tree({"RK-Old": {}}))
        guarded = ReadOnlyFTP(ftp, read_only=True)
        device_name, project_name, target, inside = navigate_to_work_orders(
            guarded, "T48", "Project A", dry_run=True
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(_sample_zip("RK-"), Path(temp_name))
            report = compare_work_orders(
                guarded,
                staging,
                device_name,
                project_name,
                target,
                "RK-",
                "Default",
                inside,
            )
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(ftp.stored, [])
        self.assertEqual(report.banner, DRY_RUN_BANNER)
        actions = {row.work_order: row.action for row in report.rows}
        self.assertEqual(actions["RK-Old"], "Skip")
        self.assertEqual(actions["RK-New"], "Would Upload")

    def test_upload_skips_existing_work_order(self):
        ftp = FakeFTP(_device_tree({"RK-Old": {}}))
        navigate_to_work_orders(ftp, "T48", "Project A", dry_run=False)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(_sample_zip("RK-"), Path(temp_name))
            report = upload_work_orders(ftp, staging, "RK-", "Default", "T48", "Project A")
        self.assertEqual(report.skipped_existing_work_orders, 1)
        stored_paths = [path for path, _data in ftp.stored]
        self.assertTrue(any(path.endswith("/RK-New/notes.txt") for path in stored_paths))
        self.assertFalse(any("/RK-Old/" in path for path in stored_paths))

    def test_race_recheck_skips_work_order_created_after_preview(self):
        ftp = FakeFTP(_device_tree())
        navigate_to_work_orders(ftp, "T48", "Project A", dry_run=False)
        ftp.mkd_calls.clear()
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            only = root / "Work Orders" / "RK-New"
            only.mkdir(parents=True)
            (only / "notes.txt").write_text("notes", encoding="utf-8")
            staging = root / "Work Orders"
            listings = iter([[], ["RK-New"]])

            def fake_list(_ftp):
                return next(listings)

            with patch("app.ftp_client.ftp_list_directories", side_effect=fake_list):
                _uploaded, _dirs, skipped, rows = upload_tree(ftp, staging, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(rows[0].action, "Skip — Already Exists")

    def test_rejects_path_tricks(self):
        with self.assertRaises(RuntimeError):
            validate_remote_name("../T48")


class ZipRoundTripTests(unittest.TestCase):
    def test_staged_zip_contains_placeholder(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("DK-Job/", b"")
            archive.writestr("DK-Job/notes.txt", b"notes")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "in"
            root.mkdir()
            with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
                archive.extractall(root)
            payload, _report = build_work_orders(root, "DK-", "RK-")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(archive.read("RK-Job/notes.txt"), b"notes")
            self.assertEqual(archive.read("RK-Job/RK-Job"), PLACEHOLDER_DATA.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
