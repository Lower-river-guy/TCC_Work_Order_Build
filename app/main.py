"""Cloud Run web app for building and uploading TCC work orders."""

from __future__ import annotations

import hmac
import os
import tempfile
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from app import ftp_client
from app.builder import build_work_orders, extract_template_zip
from app.settings import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_REPLACE,
    DEFAULT_SEARCH,
    ZIP_FILE_NAME,
    max_upload_bytes,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = max_upload_bytes()

    @app.before_request
    def require_access_token():
        if request.path in {"/health", "/api/config"}:
            return None
        expected = os.environ.get("APP_ACCESS_TOKEN", "").strip()
        if not expected:
            return None
        provided = (
            request.headers.get("X-Access-Token", "")
            or request.form.get("access_token", "")
            or request.args.get("access_token", "")
        )
        if not _token_matches(provided, expected):
            return jsonify(error="Unauthorized"), 401
        return None

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            app_name=APP_NAME,
            version=APP_VERSION,
            default_search=DEFAULT_SEARCH,
            default_replace=DEFAULT_REPLACE,
        )

    @app.get("/health")
    def health():
        return jsonify(status="ok", version=APP_VERSION)

    @app.get("/api/config")
    def config():
        return jsonify(
            version=APP_VERSION,
            access_required=bool(os.environ.get("APP_ACCESS_TOKEN", "").strip()),
            ftp_configured=ftp_client.credentials_configured(),
            default_search=DEFAULT_SEARCH,
            default_replace=DEFAULT_REPLACE,
        )

    @app.post("/api/preview")
    def preview():
        try:
            _zip_bytes, report = _build_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        return jsonify(
            work_orders=report.work_orders,
            existing_files=report.existing_files,
            placeholder_files=report.placeholder_files,
            output_folders=report.output_folders,
            directory_entries=report.directory_entries,
            skipped_files=report.skipped_files,
            log=report.log,
        )

    @app.post("/api/build")
    def build():
        try:
            zip_bytes, report = _build_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        download = BytesIO(zip_bytes)
        response = send_file(
            download,
            mimetype="application/zip",
            as_attachment=True,
            download_name=ZIP_FILE_NAME,
        )
        response.headers["X-Work-Orders"] = str(len(report.work_orders))
        return response

    @app.get("/api/ftp/devices")
    def ftp_devices():
        try:
            ftp = ftp_client.connect_ftp()
        except RuntimeError as error:
            return jsonify(error=str(error)), 400
        try:
            devices = ftp_client.list_devices(ftp)
        except Exception as error:
            return jsonify(error=_public_error(error)), 502
        finally:
            _close_ftp(ftp)
        return jsonify(devices=devices)

    @app.get("/api/ftp/projects")
    def ftp_projects():
        device = request.args.get("device", "")
        try:
            ftp = ftp_client.connect_ftp()
        except RuntimeError as error:
            return jsonify(error=str(error)), 400
        try:
            projects = ftp_client.list_projects(ftp, device)
        except RuntimeError as error:
            return jsonify(error=str(error)), 400
        except Exception as error:
            return jsonify(error=_public_error(error)), 502
        finally:
            _close_ftp(ftp)
        return jsonify(device=device, projects=projects)

    @app.post("/api/ftp/upload")
    def ftp_upload():
        dry_run = _wants_dry_run()
        device = request.form.get("device", "")
        project = request.form.get("project", "")
        try:
            zip_bytes, _report = _build_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400

        try:
            ftp = ftp_client.connect_ftp()
        except RuntimeError as error:
            return jsonify(error=str(error)), 400

        try:
            with tempfile.TemporaryDirectory(prefix="tcc-stage-") as temp_name:
                staging = ftp_client.stage_work_orders(zip_bytes, Path(temp_name))
                result = ftp_client.upload_work_orders(ftp, staging, device, project, dry_run)
        except RuntimeError as error:
            return jsonify(error=str(error)), 400
        except Exception as error:
            return jsonify(error=_public_error(error)), 502
        finally:
            _close_ftp(ftp)

        return jsonify(
            dry_run=result.dry_run,
            device=result.device,
            project=result.project,
            target=result.target,
            directories=result.directories,
            files=result.files,
            skipped_existing_work_orders=result.skipped_existing_work_orders,
            log=result.log,
        )

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="Upload exceeds the size limit."), 413

    return app


def _token_matches(provided: str, expected: str) -> bool:
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(provided_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(provided_bytes, expected_bytes)


def _wants_dry_run() -> bool:
    raw = request.form.get("dry_run", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _build_from_request():
    upload = request.files.get("template")
    if upload is None or not upload.filename:
        raise ValueError("Choose a ZIP of the work-order template folders.")
    if not upload.filename.lower().endswith(".zip"):
        raise ValueError("The template must be a .zip file.")
    payload = upload.read()
    if not payload:
        raise ValueError("The uploaded ZIP is empty.")
    search = request.form.get("search", DEFAULT_SEARCH)
    replacement = request.form.get("replace", DEFAULT_REPLACE)
    with tempfile.TemporaryDirectory(prefix="tcc-template-") as temp_name:
        input_root = extract_template_zip(payload, Path(temp_name))
        return build_work_orders(input_root, search, replacement)


def _close_ftp(ftp) -> None:
    try:
        ftp.quit()
    except Exception:
        try:
            ftp.close()
        except Exception:
            pass


def _public_error(error: Exception) -> str:
    text = str(error).strip() or type(error).__name__
    return f"{type(error).__name__}: {text}"


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
