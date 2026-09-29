"""Web API tests using the Flask test client and a fake FTP session."""



from __future__ import annotations



import io

import os

import unittest

import zipfile

from unittest.mock import patch



from app.main import create_app

from app.settings import APP_VERSION, DEFAULT_PREFIX

from tests.fake_ftp import FakeFTP





def _master_zip() -> bytes:

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:

        archive.writestr("DK-Job/notes.txt", b"notes")

    return buffer.getvalue()





def _custom_zip() -> bytes:

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:

        archive.writestr("DK-Custom/notes.txt", b"custom")

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

            for key in ("APP_ACCESS_TOKEN", "TCC_T48_DEVICE_USER", "TCC_T48_DEVICE_PASS")

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



    def test_health_and_page_ui(self):

        health = self.client.get("/health")

        self.assertEqual(health.get_json()["version"], APP_VERSION)

        page = self.client.get("/")

        html = page.data.decode("utf-8")

        self.assertNotIn("Grade Checker", html)

        self.assertIn("Sukut Work Order Builder", html)

        self.assertIn("Work Order Steps", html)

        self.assertIn("Work Order Preset", html)

        self.assertIn('name="work_order_preset"', html)

        self.assertIn("rkolt@sukut.com", html)

        self.assertIn("Template Source", html)

        self.assertIn('value="default"', html)

        self.assertIn('value="upload"', html)

        self.assertIn('value="none"', html)

        self.assertIn('name="template_source"', html)

        self.assertIn('id="custom-work-order-names"', html)

        self.assertIn('id="dry-run" type="checkbox" checked', html)

        self.assertIn(f'app.js?v={APP_VERSION}', html)

        self.assertIn("Total Work Orders", html)

        self.assertIn("<th>Source</th>", html)



    def test_config_defaults(self):

        config = self.client.get("/api/config").get_json()

        self.assertEqual(config["default_prefix"], DEFAULT_PREFIX)

        self.assertTrue(config["dry_run_default"])



    def test_default_template_preview(self):

        ftp = FakeFTP(_tree())

        with patch("app.template_source.fetch_master_template_bytes", return_value=_master_zip()):

            with patch("app.workflow.connect_ftp", return_value=ftp):

                response = self.client.post(

                    "/api/work-orders/preview",

                    data={

                        "prefix": "RK-",

                        "device": "T48",

                        "project": "Project A",

                        "template_source": "default",

                    },

                )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        body = response.get_json()

        self.assertEqual(body["template"], "Default")

        self.assertEqual(body["rows"][0]["work_order"], "RK-Job")

        self.assertEqual(body["rows"][0]["source"], "Default")



    def test_custom_template_preview(self):

        ftp = FakeFTP(_tree())

        with patch("app.template_source.fetch_master_template_bytes") as mock_fetch:

            with patch("app.workflow.connect_ftp", return_value=ftp):

                response = self.client.post(

                    "/api/work-orders/preview",

                    data={

                        "prefix": "MH-",

                        "device": "T48",

                        "project": "Project A",

                        "template_source": "upload",

                        "custom_template": (io.BytesIO(_custom_zip()), "custom.zip"),

                    },

                    content_type="multipart/form-data",

                )

        mock_fetch.assert_not_called()

        self.assertEqual(response.status_code, 200)

        body = response.get_json()

        self.assertEqual(body["template"], "Uploaded — custom.zip")

        self.assertEqual(body["rows"][0]["work_order"], "MH-Custom")



    def test_no_template_with_custom_names_preview(self):

        ftp = FakeFTP(_tree())

        with patch("app.workflow.connect_ftp", return_value=ftp):

            response = self.client.post(

                "/api/work-orders/preview",

                data={

                    "prefix": "RK-",

                    "device": "T48",

                    "project": "Project A",

                    "template_source": "none",

                    "custom_work_order_names": "Test, Test 2, Test 3",

                },

            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        body = response.get_json()

        self.assertEqual(body["totals"]["total"], 3)

        names = [row["work_order"] for row in body["rows"]]

        self.assertEqual(names, ["RK-Test", "RK-Test 2", "RK-Test 3"])

        self.assertTrue(all(row["source"] == "Custom" for row in body["rows"]))



    def test_no_template_without_names_rejected(self):

        response = self.client.post(

            "/api/work-orders/preview",

            data={

                "prefix": "RK-",

                "device": "T48",

                "project": "Project A",

                "template_source": "none",

            },

        )

        self.assertEqual(response.status_code, 400)



    def test_custom_names_with_default_template(self):

        ftp = FakeFTP(_tree())

        with patch("app.template_source.fetch_master_template_bytes", return_value=_master_zip()):

            with patch("app.workflow.connect_ftp", return_value=ftp):

                response = self.client.post(

                    "/api/work-orders/preview",

                    data={

                        "prefix": "RK-",

                        "device": "T48",

                        "project": "Project A",

                        "template_source": "default",

                        "custom_work_order_names": "Test, Test 2",

                    },

                )

        self.assertEqual(response.status_code, 200)

        body = response.get_json()

        names = {row["work_order"]: row["source"] for row in body["rows"]}

        self.assertEqual(names["RK-Job"], "Default")

        self.assertEqual(names["RK-Test"], "Custom")



    def test_dry_run_zero_writes(self):

        ftp = FakeFTP(_tree())

        with patch("app.template_source.fetch_master_template_bytes", return_value=_master_zip()):

            with patch("app.workflow.connect_ftp", return_value=ftp):

                response = self.client.post(

                    "/api/work-orders/run",

                    data={

                        "prefix": "RK-",

                        "device": "T48",

                        "project": "Project A",

                        "template_source": "default",

                        "dry_run": "true",

                    },

                )

        self.assertTrue(response.get_json()["dry_run"])

        self.assertEqual(ftp.mkd_calls, [])



    def test_live_upload_requires_confirmation(self):

        with patch("app.template_source.fetch_master_template_bytes", return_value=_master_zip()):

            response = self.client.post(

                "/api/work-orders/run",

                data={

                    "prefix": "RK-",

                    "device": "T48",

                    "project": "Project A",

                    "template_source": "default",

                    "dry_run": "false",

                    "confirm_upload": "false",

                },

            )

        self.assertEqual(response.status_code, 400)



    def test_invalid_prefix_rejected(self):

        response = self.client.post(

            "/api/work-orders/preview",

            data={

                "prefix": "../RK-",

                "device": "T48",

                "project": "Project A",

                "template_source": "default",

            },

        )

        self.assertEqual(response.status_code, 400)





if __name__ == "__main__":

    unittest.main()

