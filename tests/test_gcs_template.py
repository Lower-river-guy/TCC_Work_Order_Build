import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.workflow import build_staging_from_master


def _master_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("DK-Asbuilt/notes.txt", b"notes")
    return buffer.getvalue()


class GcsTemplateTests(unittest.TestCase):
    @patch("app.workflow.fetch_master_template_bytes", return_value=_master_zip_bytes())
    def test_workflow_reads_master_template_from_gcs(self, _mock_fetch):
        with tempfile.TemporaryDirectory() as temp_name:
            staging, names, checker = build_staging_from_master("ryan-kolt", Path(temp_name))
            self.assertEqual(checker.prefix, "RK-")
            self.assertEqual(names, ["RK-Asbuilt"])
            self.assertTrue((staging / "RK-Asbuilt").is_dir())


if __name__ == "__main__":
    unittest.main()
