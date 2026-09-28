import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.template_source import load_template_zip_bytes, prepare_template_root, validate_custom_template_bytes
from app.workflow import OperationRequest, build_staging


def _zip_with_folder(folder: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{folder}/notes.txt", b"notes")
    return buffer.getvalue()


class TemplateSourceTests(unittest.TestCase):
    @patch("app.template_source.fetch_master_template_bytes", return_value=_zip_with_folder("DK-Job"))
    def test_default_template_from_gcs(self, mock_fetch):
        payload, selection = load_template_zip_bytes(use_default=True, custom_bytes=None, custom_filename=None)
        self.assertEqual(selection.label, "Default")
        self.assertTrue(payload)
        mock_fetch.assert_called_once()

    def test_custom_template_does_not_call_gcs(self):
        custom = _zip_with_folder("DK-Custom")
        with patch("app.template_source.fetch_master_template_bytes") as mock_fetch:
            payload, selection = load_template_zip_bytes(
                use_default=False,
                custom_bytes=custom,
                custom_filename="mine.zip",
            )
        mock_fetch.assert_not_called()
        self.assertEqual(selection.label, "Custom — mine.zip")
        self.assertEqual(payload, custom)

    def test_corrupt_zip_rejected(self):
        with self.assertRaises(ValueError):
            validate_custom_template_bytes(b"not-a-zip", "bad.zip")

    def test_invalid_template_structure_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", b"no folders")
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as temp_name:
                prepare_template_root(buffer.getvalue(), Path(temp_name))

    def test_zip_slip_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../escape.txt", b"nope")
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as temp_name:
                prepare_template_root(buffer.getvalue(), Path(temp_name))

    @patch("app.template_source.fetch_master_template_bytes", return_value=_zip_with_folder("DK-One"))
    def test_custom_build_uses_temp_directory(self, _mock_fetch):
        custom = _zip_with_folder("DK-Two")
        request = OperationRequest(
            prefix="MH-",
            device="T48",
            project="Project A",
            use_default_template=False,
            custom_bytes=custom,
            custom_filename="custom.zip",
        )
        with tempfile.TemporaryDirectory(prefix="tcc-test-") as temp_name:
            staging, names, prefix, template = build_staging(request, Path(temp_name))
            self.assertEqual(prefix, "MH-")
            self.assertEqual(template.label, "Custom — custom.zip")
            self.assertEqual(names, ["MH-Two"])
            self.assertTrue(staging.exists())


if __name__ == "__main__":
    unittest.main()
