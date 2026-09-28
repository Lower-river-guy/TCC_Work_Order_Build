"""Tests for optional custom work order creation."""

from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.custom_work_order import (
    add_custom_work_order_to_staging,
    materialize_custom_work_order,
    resolve_custom_work_order_folder,
    validate_custom_work_order_name,
)
from app.ftp_client import compare_work_orders, navigate_to_work_orders, stage_work_orders, upload_tree
from app.ftp_guard import ReadOnlyFTP
from app.settings import OUTPUT_SUBFOLDER_NAME, PLACEHOLDER_DATA
from app.workflow import OperationRequest, build_staging
from tests.fake_ftp import FakeFTP
from tests.test_ftp import _device_tree, _sample_zip


class CustomWorkOrderNameTests(unittest.TestCase):
    def test_wall_drains_with_rk_prefix(self):
        self.assertEqual(resolve_custom_work_order_folder("RK-", "Wall Drains"), "RK-Wall Drains")

    def test_prefixed_name_does_not_duplicate(self):
        self.assertEqual(
            resolve_custom_work_order_folder("RK-", "RK-Wall Drains"),
            "RK-Wall Drains",
        )

    def test_rejects_blank(self):
        with self.assertRaises(ValueError):
            validate_custom_work_order_name("   ")

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_custom_work_order_name("../Wall Drains")


class CustomWorkOrderStructureTests(unittest.TestCase):
    def test_structure_matches_worksmanager(self):
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name)
            folder = "RK-Wall Drains"
            materialize_custom_work_order(staging, folder)
            work_order_dir = staging / folder
            placeholder = work_order_dir / folder
            self.assertTrue(work_order_dir.is_dir())
            self.assertTrue((work_order_dir / OUTPUT_SUBFOLDER_NAME).is_dir())
            self.assertTrue(placeholder.is_file())
            self.assertEqual(placeholder.name, folder)
            self.assertEqual(placeholder.suffix, "")
            self.assertEqual(placeholder.read_bytes(), b"11\r\n")
            self.assertEqual(placeholder.read_bytes(), PLACEHOLDER_DATA.encode("utf-8"))


class CustomWorkOrderWorkflowTests(unittest.TestCase):
    def test_preview_includes_custom_in_totals(self):
        ftp = FakeFTP(_device_tree())
        guarded = ReadOnlyFTP(ftp, read_only=True)
        device_name, project_name, target, inside = navigate_to_work_orders(
            guarded, "T48", "Project A", dry_run=True
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(_sample_zip("RK-"), Path(temp_name))
            add_custom_work_order_to_staging(
                staging, "RK-", enabled=True, raw_name="Wall Drains"
            )
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
        names = {row.work_order for row in report.rows}
        self.assertIn("RK-Wall Drains", names)
        self.assertEqual(report.totals["total"], 3)

    def test_dry_run_zero_writes_with_custom(self):
        ftp = FakeFTP(_device_tree())
        guarded = ReadOnlyFTP(ftp, read_only=True)
        navigate_to_work_orders(guarded, "T48", "Project A", dry_run=True)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(_sample_zip("RK-"), Path(temp_name))
            add_custom_work_order_to_staging(
                staging, "RK-", enabled=True, raw_name="Wall Drains"
            )
            compare_work_orders(
                guarded,
                staging,
                "T48",
                "Project A",
                "/target",
                "RK-",
                "Default",
                True,
            )
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(ftp.stored, [])

    def test_existing_custom_skipped_on_upload(self):
        ftp = FakeFTP(_device_tree({"RK-Wall Drains": {}}))
        navigate_to_work_orders(ftp, "T48", "Project A", dry_run=False)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name) / "Work Orders"
            staging.mkdir()
            materialize_custom_work_order(staging, "RK-Wall Drains")
            _uploaded, _dirs, skipped, rows = upload_tree(ftp, staging, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(rows[0].status, "Existing")
        self.assertFalse(any("RK-Wall Drains" in path for path, _ in ftp.stored))

    def test_missing_custom_uploads_placeholder_and_output(self):
        ftp = FakeFTP(_device_tree())
        navigate_to_work_orders(ftp, "T48", "Project A", dry_run=False)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name) / "Work Orders"
            staging.mkdir()
            materialize_custom_work_order(staging, "RK-Wall Drains")
            upload_tree(ftp, staging, [])
        stored_paths = [path for path, _data in ftp.stored]
        self.assertTrue(any(path.endswith("/RK-Wall Drains/RK-Wall Drains") for path in stored_paths))
        self.assertTrue(any("RK-Wall Drains/Output" in path or path.endswith("/Output") for path in ftp.mkd_calls))

    @patch("app.template_source.fetch_master_template_bytes")
    def test_default_gcs_template_still_works(self, mock_fetch):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("DK-Job/notes.txt", b"notes")
        mock_fetch.return_value = buffer.getvalue()
        request = OperationRequest(
            prefix="RK-",
            device="T48",
            project="Project A",
            use_default_template=True,
            add_custom_work_order=False,
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging, names, prefix, template = build_staging(request, Path(temp_name))
            self.assertEqual(prefix, "RK-")
            self.assertEqual(template.label, "Default")
            self.assertEqual(names, ["RK-Job"])
            child_names = {path.name for path in staging.iterdir() if path.is_dir()}
            self.assertIn("RK-Job", child_names)

    def test_custom_zip_template_still_works(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("DK-Custom/notes.txt", b"x")
        request = OperationRequest(
            prefix="MH-",
            device="T48",
            project="Project A",
            use_default_template=False,
            custom_bytes=buffer.getvalue(),
            custom_filename="mine.zip",
            add_custom_work_order=True,
            custom_work_order_name="Extra",
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging, names, _prefix, template = build_staging(request, Path(temp_name))
            self.assertEqual(template.label, "Custom — mine.zip")
            self.assertIn("MH-Custom", names)
            self.assertIn("MH-Extra", names)
            self.assertTrue((staging / "MH-Extra" / "MH-Extra").is_file())


if __name__ == "__main__":
    unittest.main()
