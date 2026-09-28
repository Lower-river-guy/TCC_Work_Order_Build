"""Tests for comma-separated custom work orders."""

from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.custom_work_order import (
    add_custom_work_orders_to_staging,
    materialize_custom_work_order,
    parse_comma_separated_base_names,
    resolve_custom_work_order_folder,
    resolve_custom_work_order_folders,
    validate_custom_base_name,
)
from app.ftp_client import compare_work_orders, navigate_to_work_orders, stage_work_orders, upload_tree
from app.ftp_guard import ReadOnlyFTP
from app.settings import OUTPUT_SUBFOLDER_NAME, PLACEHOLDER_DATA
from app.template_source import TEMPLATE_SOURCE_NONE, TEMPLATE_SOURCE_UPLOAD
from app.workflow import OperationRequest, build_staging
from tests.fake_ftp import FakeFTP
from tests.test_ftp import _device_tree, _sample_zip


class CustomNameParsingTests(unittest.TestCase):
    def test_comma_separated_names(self):
        self.assertEqual(parse_comma_separated_base_names("Test,Test 2,Test 3"), ["Test", "Test 2", "Test 3"])

    def test_spaces_around_commas(self):
        self.assertEqual(parse_comma_separated_base_names("Test , Test 2 , Test 3"), ["Test", "Test 2", "Test 3"])

    def test_empty_entries_ignored(self):
        self.assertEqual(parse_comma_separated_base_names("Test,,Test 2, ,Test 3"), ["Test", "Test 2", "Test 3"])

    def test_prefix_applied_to_all(self):
        folders = resolve_custom_work_order_folders("MH-", "Test,Test 2,Test 3")
        self.assertEqual(folders, ["MH-Test", "MH-Test 2", "MH-Test 3"])

    def test_changing_prefix_changes_folders(self):
        first = resolve_custom_work_order_folders("RK-", "Test")
        second = resolve_custom_work_order_folders("MH-", "Test")
        self.assertEqual(first, ["RK-Test"])
        self.assertEqual(second, ["MH-Test"])

    def test_prefix_not_duplicated(self):
        self.assertEqual(resolve_custom_work_order_folder("RK-", "RK-Test"), "RK-Test")

    def test_case_insensitive_duplicate_detection(self):
        with self.assertRaises(ValueError):
            resolve_custom_work_order_folders("RK-", "Test, test")

    def test_invalid_name_identified(self):
        with self.assertRaisesRegex(ValueError, '"Bad/Name"'):
            validate_custom_base_name("Bad/Name")


class CustomStructureTests(unittest.TestCase):
    def test_placeholder_structure(self):
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name)
            folder = "RK-Test"
            materialize_custom_work_order(staging, folder)
            work_order_dir = staging / folder
            placeholder = work_order_dir / folder
            self.assertTrue((work_order_dir / OUTPUT_SUBFOLDER_NAME).is_dir())
            self.assertTrue(placeholder.is_file())
            self.assertEqual(placeholder.suffix, "")
            self.assertEqual(placeholder.name, folder)
            self.assertEqual(placeholder.read_bytes(), b"11\r\n")
            self.assertEqual(placeholder.read_bytes(), PLACEHOLDER_DATA.encode("utf-8"))


class CustomWorkflowTests(unittest.TestCase):
    @patch("app.template_source.fetch_master_template_bytes")
    def test_default_template_plus_custom_names(self, mock_fetch):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("DK-Job/notes.txt", b"x")
        mock_fetch.return_value = buffer.getvalue()
        request = OperationRequest(
            prefix="RK-",
            device="T48",
            project="Project A",
            template_source="default",
            custom_work_order_names="Test, Test 2",
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging, names, _prefix, _template, sources = build_staging(request, Path(temp_name))
        self.assertIn("RK-Job", names)
        self.assertIn("RK-Test", names)
        self.assertIn("RK-Test 2", names)
        self.assertEqual(sources["RK-Job"], "Default")
        self.assertEqual(sources["RK-Test"], "Custom")

    def test_uploaded_zip_plus_custom_names(self):
        custom = io.BytesIO()
        with zipfile.ZipFile(custom, "w") as archive:
            archive.writestr("DK-A/notes.txt", b"a")
        request = OperationRequest(
            prefix="RK-",
            device="T48",
            project="Project A",
            template_source=TEMPLATE_SOURCE_UPLOAD,
            custom_bytes=custom.getvalue(),
            custom_filename="mine.zip",
            custom_work_order_names="Extra",
        )
        with tempfile.TemporaryDirectory() as temp_name:
            _staging, names, _prefix, template, sources = build_staging(request, Path(temp_name))
        self.assertEqual(template.kind, TEMPLATE_SOURCE_UPLOAD)
        self.assertIn("RK-A", names)
        self.assertIn("RK-Extra", names)
        self.assertEqual(sources["RK-A"], "Uploaded Template")
        self.assertEqual(sources["RK-Extra"], "Custom")

    def test_no_template_custom_only(self):
        request = OperationRequest(
            prefix="RK-",
            device="T48",
            project="Project A",
            template_source=TEMPLATE_SOURCE_NONE,
            custom_work_order_names="Test,Test 2,Test 3",
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging, names, _prefix, template, sources = build_staging(request, Path(temp_name))
            self.assertEqual(template.kind, TEMPLATE_SOURCE_NONE)
            self.assertEqual(names, ["RK-Test", "RK-Test 2", "RK-Test 3"])
            self.assertTrue(all(sources[name] == "Custom" for name in names))
            self.assertTrue((staging / "RK-Test" / "RK-Test").is_file())

    def test_preview_includes_source_and_totals(self):
        ftp = FakeFTP(_device_tree({"RK-Test 2": {}}))
        guarded = ReadOnlyFTP(ftp, read_only=True)
        device_name, project_name, target, inside = navigate_to_work_orders(
            guarded, "T48", "Project A", dry_run=True
        )
        with tempfile.TemporaryDirectory() as temp_name:
            staging = stage_work_orders(_sample_zip("RK-"), Path(temp_name))
            add_custom_work_orders_to_staging(staging, "RK-", "Test, Test 2, Test 3")
            sources = {"RK-New": "Default", "RK-Old": "Default", "RK-Test": "Custom", "RK-Test 2": "Custom", "RK-Test 3": "Custom"}
            report = compare_work_orders(
                guarded,
                staging,
                device_name,
                project_name,
                target,
                "RK-",
                "Default",
                inside,
                staging_sources=sources,
            )
        self.assertEqual(report.totals["total"], 5)
        by_name = {row.work_order: row for row in report.rows}
        self.assertEqual(by_name["RK-Test"].source, "Custom")
        self.assertEqual(by_name["RK-Test 2"].status, "Existing")

    def test_dry_run_zero_writes(self):
        ftp = FakeFTP(_device_tree())
        guarded = ReadOnlyFTP(ftp, read_only=True)
        navigate_to_work_orders(guarded, "T48", "Project A", dry_run=True)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name) / "Work Orders"
            staging.mkdir()
            add_custom_work_orders_to_staging(staging, "RK-", "Test")
            compare_work_orders(guarded, staging, "T48", "Project A", "/t", "RK-", "None", True)
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(ftp.stored, [])

    def test_existing_custom_skipped_on_upload(self):
        ftp = FakeFTP(_device_tree({"RK-Test": {}}))
        navigate_to_work_orders(ftp, "T48", "Project A", dry_run=False)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name) / "Work Orders"
            staging.mkdir()
            materialize_custom_work_order(staging, "RK-Test")
            _uploaded, _dirs, skipped, rows = upload_tree(ftp, staging, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(rows[0].status, "Existing")
        self.assertFalse(ftp.stored)

    def test_missing_custom_uploads_structure(self):
        ftp = FakeFTP(_device_tree())
        navigate_to_work_orders(ftp, "T48", "Project A", dry_run=False)
        with tempfile.TemporaryDirectory() as temp_name:
            staging = Path(temp_name) / "Work Orders"
            staging.mkdir()
            materialize_custom_work_order(staging, "RK-Test")
            upload_tree(ftp, staging, [])
        stored_paths = [path for path, _data in ftp.stored]
        self.assertTrue(any(path.endswith("/RK-Test/RK-Test") for path in stored_paths))
        self.assertTrue(any(path.endswith("/Output") for path in ftp.mkd_calls))


if __name__ == "__main__":
    unittest.main()
