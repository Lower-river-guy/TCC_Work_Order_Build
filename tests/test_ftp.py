"""FTP planning tests. These do not open a network connection."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.builder import build_work_orders
from app.ftp_client import (
    credentials_configured,
    get_t48_credentials,
    resolve_credentials,
    stage_work_orders,
    upload_work_orders,
    validate_remote_name,
)
from app.settings import PLACEHOLDER_DATA
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


def _sample_zip() -> bytes:
    with tempfile.TemporaryDirectory() as temp_name:
        root = Path(temp_name)
        (root / "DK-New").mkdir()
        (root / "DK-New" / "notes.txt").write_text("notes", encoding="utf-8")
        (root / "DK-Old").mkdir()
        (root / "DK-Old" / "notes.txt").write_text("old", encoding="utf-8")
        payload, _report = build_work_orders(root, "DK-", "CL-")
    return payload


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in ("TCC_T48_DEVICE_USER", "TCC_T48_DEVICE_PASS", "TCC_DEVICE_ENV_FILE")
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_credentials_name_the_variables_only(self):
        os.environ["TCC_T48_DEVICE_USER"] = "not-a-real-user"
        with self.assertRaises(RuntimeError) as caught:
            resolve_credentials()
        message = str(caught.exception)
        self.assertIn("TCC_T48_DEVICE_PASS", message)
        self.assertNotIn("not-a-real-user", message)
        self.assertFalse(credentials_configured())

    def test_env_file_keys_are_read(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "device.env"
            path.write_text(
                "TCC_T48_DEVICE_USER=example-user\nTCC_T48_DEVICE_PASS=example-pass\n",
                encoding="utf-8",
            )
            username, password = get_t48_credentials(
                {"TCC_T48_DEVICE_USER": "example-user", "TCC_T48_DEVICE_PASS": "example-pass"}
            )
            self.assertEqual((username, password), ("example-user", "example-pass"))
            os.environ["TCC_DEVICE_ENV_FILE"] = str(path)
            try:
                self.assertEqual(resolve_credentials(), ("example-user", "example-pass"))
            finally:
                os.environ.pop("TCC_DEVICE_ENV_FILE", None)


class UploadTests(unittest.TestCase):
    def test_rejects_path_tricks(self):
        with self.assertRaises(RuntimeError):
            validate_remote_name("../T48")
        with self.assertRaises(RuntimeError):
            validate_remote_name("T48/secret")

    def test_dry_run_does_not_create_or_upload(self):
        payload = _sample_zip()
        ftp = FakeFTP(_device_tree())
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(payload, Path(temp_name))
            report = upload_work_orders(ftp, staging, "T48", "Project A", dry_run=True)
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(ftp.stored, [])
        self.assertTrue(report.dry_run)
        self.assertGreater(report.files, 0)
        self.assertIn("[CHANGES MADE] NONE", report.log)
        self.assertTrue(report.target.endswith("/Work Orders"))

    def test_upload_skips_existing_work_order(self):
        payload = _sample_zip()
        ftp = FakeFTP(_device_tree({"CL-Old": {}}))
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(payload, Path(temp_name))
            report = upload_work_orders(ftp, staging, "t48", "project a", dry_run=False)
        self.assertEqual(report.device, "T48")
        self.assertEqual(report.project, "Project A")
        self.assertEqual(report.skipped_existing_work_orders, 1)
        stored_paths = [path for path, _data in ftp.stored]
        self.assertTrue(any(path.endswith("/CL-New/notes.txt") for path in stored_paths))
        self.assertFalse(any("/CL-Old/" in path for path in stored_paths))
        placeholder = next(data for path, data in ftp.stored if path.endswith("/CL-New/CL-New"))
        self.assertEqual(placeholder, PLACEHOLDER_DATA.encode("utf-8"))

    def test_missing_project_container_makes_no_folders(self):
        tree = _device_tree()
        del tree["TCC"]["sukut"]["trimblesynchronizerdata"]["T48"]["Trimble SCS900 Data"]
        ftp = FakeFTP(tree)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(_sample_zip(), Path(temp_name))
            with self.assertRaises(RuntimeError):
                upload_work_orders(ftp, staging, "T48", "Project A", dry_run=False)
        self.assertEqual(ftp.mkd_calls, [])


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
            payload, _report = build_work_orders(root, "DK-", "CL-")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(archive.read("CL-Job/notes.txt"), b"notes")


if __name__ == "__main__":
    unittest.main()
