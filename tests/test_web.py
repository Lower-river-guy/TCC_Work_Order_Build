"""Web API tests using the Flask test client and a fake FTP session."""

from __future__ import annotations

import io
import os
import unittest
import zipfile
from unittest.mock import patch

from app.main import create_app
from tests.fake_ftp import FakeFTP


def _template_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Template/DK-Job/notes.txt", b"notes")
    return buffer.getvalue()


def _tree() -> dict:
    return {
        "TCC": {
            "sukut": {
                "trimblesynchronizerdata": {
                    "T48": {
                        "Trimble SCS900 Data": {
                            "Project A": {},
                        }
                    }
                }
            }
        }
    }


class WebTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "APP_ACCESS_TOKEN",
                "TCC_T48_DEVICE_USER",
                "TCC_T48_DEVICE_PASS",
                "TCC_DEVICE_ENV_FILE",
            )
        }
        for key in self._saved:
            os.environ.pop(key, None)
        self.client = create_app().test_client()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _post_template(self, url: str, **extra):
        data = {
            "template": (io.BytesIO(_template_zip()), "template.zip"),
            "search": "DK-",
            "replace": "CL-",
        }
        data.update(extra)
        return self.client.post(url, data=data)

    def test_health_and_page(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["version"], "0.01.00")
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"TCC Work Order Builder", page.data)
        config = self.client.get("/api/config").get_json()
        self.assertFalse(config["ftp_configured"])
        self.assertFalse(config["access_required"])

    def test_preview_and_download(self):
        preview = self._post_template("/api/preview")
        self.assertEqual(preview.status_code, 200)
        body = preview.get_json()
        self.assertEqual(body["work_orders"], ["CL-Job"])
        self.assertEqual(body["placeholder_files"], 1)
        self.assertGreaterEqual(body["output_folders"], 1)

        download = self._post_template("/api/build")
        self.assertEqual(download.status_code, 200)
        self.assertIn("Work Orders.zip", download.headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
            self.assertEqual(archive.read("CL-Job/notes.txt"), b"notes")

    def test_missing_file_is_rejected(self):
        response = self.client.post("/api/preview", data={"search": "DK-", "replace": "CL-"})
        self.assertEqual(response.status_code, 400)

    def test_access_token_gates_routes_but_not_health(self):
        os.environ["APP_ACCESS_TOKEN"] = "local-test-token"
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 401)
        allowed = self.client.get("/", headers={"X-Access-Token": "local-test-token"})
        self.assertEqual(allowed.status_code, 200)

    def test_ftp_dry_run_is_the_default_and_makes_no_changes(self):
        ftp = FakeFTP(_tree())
        with patch("app.ftp_client.connect_ftp", return_value=ftp):
            response = self._post_template("/api/ftp/upload", device="T48", project="Project A")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["dry_run"])
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(ftp.stored, [])
        self.assertIn("Project A", body["target"])

    def test_ftp_upload_writes_only_when_dry_run_is_off(self):
        ftp = FakeFTP(_tree())
        with patch("app.ftp_client.connect_ftp", return_value=ftp):
            response = self._post_template(
                "/api/ftp/upload",
                device="T48",
                project="Project A",
                dry_run="false",
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["dry_run"])
        self.assertTrue(ftp.mkd_calls)
        self.assertTrue(any(path.endswith("/CL-Job/notes.txt") for path, _data in ftp.stored))

    def test_device_list_and_rejected_project_name(self):
        ftp = FakeFTP(_tree())
        with patch("app.ftp_client.connect_ftp", return_value=ftp):
            devices = self.client.get("/api/ftp/devices")
            projects = self.client.get("/api/ftp/projects?device=T48")
            rejected = self.client.get("/api/ftp/projects?device=../T48")
        self.assertEqual(devices.get_json()["devices"], ["T48"])
        self.assertEqual(projects.get_json()["projects"], ["Project A"])
        self.assertEqual(rejected.status_code, 400)


if __name__ == "__main__":
    unittest.main()
