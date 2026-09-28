"""Cloud Run web app for building and uploading TCC work orders."""

from __future__ import annotations

import hmac
import os

from flask import Flask, jsonify, render_template, request

from app import ftp_client, workflow
from app.grade_checkers import grade_checkers_for_api
from app.settings import APP_NAME, APP_VERSION


def create_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def require_access_token():
        if request.path in {"/health", "/api/config"}:
            return None
        expected = os.environ.get("APP_ACCESS_TOKEN", "").strip()
        if not expected:
            return None
        provided = request.headers.get("X-Access-Token", "") or request.args.get("access_token", "")
        if not provided:
            provided = request.form.get("access_token", "")
        if not provided and request.is_json:
            payload = request.get_json(silent=True) or {}
            provided = payload.get("access_token", "")
        if not _token_matches(provided, expected):
            return jsonify(error="Unauthorized"), 401
        return None

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            app_name=APP_NAME,
            version=APP_VERSION,
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
            grade_checkers=grade_checkers_for_api(),
            dry_run_default=True,
        )

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

    @app.post("/api/work-orders/preview")
    def work_orders_preview():
        payload = _json_or_form()
        try:
            grade_checker_id, device, project = _require_selection(payload)
            report = workflow.preview_on_tcc(grade_checker_id, device, project)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except FileNotFoundError as error:
            return jsonify(error=str(error)), 503
        except RuntimeError as error:
            return jsonify(error=str(error)), 400
        except Exception as error:
            return jsonify(error=_public_error(error)), 502
        return jsonify(report.as_dict())

    @app.post("/api/work-orders/run")
    def work_orders_run():
        payload = _json_or_form()
        dry_run = _parse_dry_run(payload.get("dry_run", "true"))
        confirm_upload = _parse_bool(payload.get("confirm_upload", "false"))
        try:
            grade_checker_id, device, project = _require_selection(payload)
            report = workflow.run_on_tcc(
                grade_checker_id,
                device,
                project,
                dry_run=dry_run,
                confirm_upload=confirm_upload,
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except FileNotFoundError as error:
            return jsonify(error=str(error)), 503
        except RuntimeError as error:
            return jsonify(error=str(error)), 400
        except Exception as error:
            return jsonify(error=_public_error(error)), 502
        return jsonify(report.as_dict())

    return app


def _json_or_form() -> dict:
    if request.is_json:
        return dict(request.get_json(silent=True) or {})
    return dict(request.form)


def _require_selection(payload: dict) -> tuple[str, str, str]:
    grade_checker_id = (payload.get("grade_checker_id") or "").strip()
    device = (payload.get("device") or "").strip()
    project = (payload.get("project") or "").strip()
    if not grade_checker_id:
        raise ValueError("Select a grade checker.")
    if not device or not project:
        raise ValueError("Select a device and a project.")
    return grade_checker_id, device, project


def _parse_dry_run(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _parse_bool(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _token_matches(provided: str, expected: str) -> bool:
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(provided_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(provided_bytes, expected_bytes)


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
