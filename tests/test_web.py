"""Web API tests using the Flask test client and a fake FTP session."""

from __future__ import annotations

import io
import os
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.main import create_app
from app.settings import APP_VERSION
from tests.fake_ftp import FakeFTP


def _master_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("DK-Job/notes.txt", b"notes")
    return buffer.getvalue()


def _tree() -> dict:
    return {
        "TCC": {
            "sukut": {
                "trimblesynchronizerdata": {
                    "T48": {
                        "Trimble SCS900 Data": {
                            "Project A": {"Work Orders": {}},
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

    def _json_post(self, url: str, payload: dict):
        return self.client.post(url, json=payload, content_type="application/json")

    def test_health_and_page_without_zip_controls(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["version"], APP_VERSION)
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertNotIn("Template ZIP", html)
        self.assertNotIn("Download ZIP", html)
        self.assertNotIn("Find in folder names", html)
        self.assertNotIn('name="replace"', html)
        self.assertIn('id="dry-run"', html)
        self.assertIn("checked", html)
        self.assertIn("Grade Checker", html)

    def test_config_lists_grade_checker_and_dry_run_default(self):
        config = self.client.get("/api/config").get_json()
        self.assertTrue(config["dry_run_default"])
        self.assertEqual(config["grade_checkers"][0]["prefix"], "RK-")

    def test_removed_endpoints_are_gone(self):
        self.assertEqual(self.client.post("/api/build").status_code, 404)
        self.assertEqual(self.client.post("/api/ftp/upload").status_code, 404)

    def test_preview_uses_gcs_master_template(self):
        ftp = FakeFTP(_tree())
        with patch("app.workflow.fetch_master_template_bytes", return_value=_master_zip()):
            with patch("app.workflow.connect_ftp", return_value=ftp):
                response = self._json_post(
                    "/api/work-orders/preview",
                    {
                        "grade_checker_id": "ryan-kolt",
                        "device": "T48",
                        "project": "Project A",
                    },
                )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["prefix"], "RK-")
        self.assertEqual(body["rows"][0]["work_order"], "RK-Job")
        self.assertEqual(body["rows"][0]["action"], "Would Upload")

    def test_dry_run_run_makes_no_ftp_writes(self):
        ftp = FakeFTP(_tree())
        with patch("app.workflow.fetch_master_template_bytes", return_value=_master_zip()):
            with patch("app.workflow.connect_ftp", return_value=ftp):
                response = self._json_post(
                    "/api/work-orders/run",
                    {
                        "grade_checker_id": "ryan-kolt",
                        "device": "T48",
                        "project": "Project A",
                        "dry_run": True,
                    },
                )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["dry_run"])
        self.assertEqual(ftp.mkd_calls, [])
        self.assertEqual(ftp.stored, [])

    def test_live_upload_requires_confirmation(self):
        with patch("app.workflow.fetch_master_template_bytes", return_value=_master_zip()):
            response = self._json_post(
                "/api/work-orders/run",
                {
                    "grade_checker_id": "ryan-kolt",
                    "device": "T48",
                    "project": "Project A",
                    "dry_run": False,
                    "confirm_upload": False,
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Confirm upload", response.get_json()["error"])

    def test_live_upload_after_confirmation_writes_new_only(self):
        ftp = FakeFTP(_tree())
        with patch("app.workflow.fetch_master_template_bytes", return_value=_master_zip()):
            with patch("app.workflow.connect_ftp", return_value=ftp):
                response = self._json_post(
                    "/api/work-orders/run",
                    {
                        "grade_checker_id": "ryan-kolt",
                        "device": "T48",
                        "project": "Project A",
                        "dry_run": False,
                        "confirm_upload": True,
                    },
                )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["dry_run"])
        self.assertTrue(ftp.mkd_calls)
        self.assertTrue(any(path.endswith("/RK-Job/notes.txt") for path, _data in ftp.stored))

    def test_app_js_does_not_persist_dry_run(self):
        js = Path(__file__).resolve().parents[1].joinpath("app", "static", "app.js").read_text(encoding="utf-8")
        self.assertNotIn('localStorage.setItem("dry', js)
        self.assertNotIn("localStorage.setItem('dry", js)
        self.assertIn("dryRunBox.checked = true", js)


if __name__ == "__main__":
    unittest.main()
