"""Runtime settings for the TCC Work Order Builder."""

from __future__ import annotations

import os

APP_VERSION = "0.01.00"
APP_NAME = "TCC Work Order Builder"

ZIP_FILE_NAME = "Work Orders.zip"
STAGING_FOLDER_NAME = "Work Orders"
OUTPUT_SUBFOLDER_NAME = "Output"
PLACEHOLDER_DATA = "11\r\n"

DEFAULT_SEARCH = "DK-"
DEFAULT_REPLACE = "CL-"

REMOTE_DEVICES_ROOT = "/TCC/sukut/trimblesynchronizerdata"
REMOTE_PROJECTS_CONTAINER = "Trimble SCS900 Data"
REMOTE_WORK_ORDERS_FOLDER = "Work Orders"

DEFAULT_FTP_HOST = "www.myconnectedsite.com"
DEFAULT_FTP_PORT = 21
DEFAULT_FTP_TIMEOUT = 60

MAX_UPLOAD_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024


def max_upload_bytes() -> int:
    raw = os.environ.get("MAX_UPLOAD_MB", "200").strip() or "200"
    try:
        megabytes = int(raw)
    except ValueError:
        megabytes = 200
    return max(1, megabytes) * 1024 * 1024
