"""Tests for work-order ZIP construction."""

from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path

from app.builder import (
    build_work_orders,
    ci_replace,
    extract_template_zip,
    make_unique_top_name,
)
from app.settings import PLACEHOLDER_DATA


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


class BuilderTests(unittest.TestCase):
    def test_literal_replacement_ignores_case_and_backslashes(self):
        self.assertEqual(ci_replace("old-Pad", "OLD-", "CL-\\A"), "CL-\\APad")
        self.assertEqual(ci_replace("Output", "", "NO"), "Output")

    def test_unique_top_names(self):
        used: set[str] = set()
        self.assertEqual(make_unique_top_name("CL-Pad", used), "CL-Pad")
        self.assertEqual(make_unique_top_name("cl-pad", used), "cl-pad_2")

    def test_build_renames_preserves_output_and_existing_placeholder(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            _write(root / "OLD-A" / "old-A", "keep-me")
            _write(root / "OLD-A" / "notes.txt", "notes")
            _write(root / "OLD-A" / "OLD-sub" / "OLD-sub", "sub-file")
            _write(root / "OLD-A" / "OLD-sub" / "data.txt", "data")
            _write(root / "OLD-A" / "output" / "result.txt", "result")
            _write(root / "NEW-A" / "marker.txt", "marker")
            _write(root / "out-side" / "leaf.txt", "leaf")

            payload, report = build_work_orders(root, "OLD-", "NEW-")

        self.assertEqual(report.work_orders, ["NEW-A", "NEW-A_2", "out-side"])
        self.assertEqual(report.skipped_files, 0)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertIn("NEW-A/", names)
            self.assertIn("NEW-A/Output/", names)
            self.assertNotIn("NEW-A/Output/Output/", names)
            self.assertEqual(archive.read("NEW-A/NEW-A"), PLACEHOLDER_DATA.encode("utf-8"))
            self.assertEqual(archive.read("NEW-A/marker.txt"), b"marker")
            self.assertEqual(archive.read("NEW-A_2/NEW-A_2"), b"keep-me")
            self.assertEqual(archive.read("NEW-A_2/notes.txt"), b"notes")
            self.assertEqual(archive.read("NEW-A_2/NEW-sub/NEW-sub"), b"sub-file")
            self.assertEqual(archive.read("NEW-A_2/NEW-sub/data.txt"), b"data")
            self.assertEqual(archive.read("NEW-A_2/Output/result.txt"), b"result")
            self.assertNotIn("NEW-A_2/Output/Output/", names)
            self.assertIn("NEW-A_2/NEW-sub/Output/", names)

    def test_output_folder_is_not_renamed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            _write(root / "output" / "result.txt", "result")
            _write(root / "out-side" / "leaf.txt", "leaf")
            payload, report = build_work_orders(root, "out", "zzz")

        self.assertEqual(report.work_orders, ["zzz-side", "Output"])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertIn("Output/result.txt", names)
            self.assertNotIn("Output/Output/", names)
            self.assertIn("zzz-side/leaf.txt", names)
            self.assertIn("zzz-side/Output/", names)

    def test_single_wrapper_folder_is_unwrapped(self):
        import tempfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Template/DK-Job/notes.txt", b"notes")
        with tempfile.TemporaryDirectory() as temp_name:
            root = extract_template_zip(buffer.getvalue(), Path(temp_name))
            self.assertEqual(root.name, "Template")
            payload, report = build_work_orders(root, "DK-", "CL-")
        self.assertEqual(report.work_orders, ["CL-Job"])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(archive.read("CL-Job/notes.txt"), b"notes")
            self.assertEqual(archive.read("CL-Job/CL-Job"), PLACEHOLDER_DATA.encode("utf-8"))

    def test_single_work_order_with_files_is_kept(self):
        import tempfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("DK-Job/notes.txt", b"notes")
        with tempfile.TemporaryDirectory() as temp_name:
            root = extract_template_zip(buffer.getvalue(), Path(temp_name))
            payload, report = build_work_orders(root, "DK-", "CL-")
        self.assertEqual(report.work_orders, ["CL-Job"])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIn("CL-Job/notes.txt", archive.namelist())

    def test_zip_slip_is_rejected(self):
        import tempfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../escape.txt", b"nope")
        with tempfile.TemporaryDirectory() as temp_name:
            with self.assertRaises(ValueError):
                extract_template_zip(buffer.getvalue(), Path(temp_name))

    def test_empty_template_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_name:
            with self.assertRaises(ValueError):
                build_work_orders(Path(temp_name), "DK-", "CL-")


if __name__ == "__main__":
    unittest.main()
