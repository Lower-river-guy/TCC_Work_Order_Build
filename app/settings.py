"""Runtime settings for the TCC Work Order Builder."""

from __future__ import annotations

import os

APP_VERSION = "0.01.03"
APP_NAME = "TCC Work Order Builder"

DEFAULT_PREFIX = "RK-"

ZIP_FILE_NAME = "Work Orders.zip"
STAGING_FOLDER_NAME = "Work Orders"
OUTPUT_SUBFOLDER_NAME = "Output"
PLACEHOLDER_DATA = "11\r\n"

MASTER_TEMPLATE_SEARCH = "DK-"

GCS_TEMPLATE_BUCKET = "trimble-data-bucket-rk"
GCS_TEMPLATE_OBJECT = "tcc-work-order-builder/templates/Work Orders.zip"

REMOTE_DEVICES_ROOT = "/TCC/sukut/trimblesynchronizerdata"
REMOTE_PROJECTS_CONTAINER = "Trimble SCS900 Data"
REMOTE_WORK_ORDERS_FOLDER = "Work Orders"

DEFAULT_FTP_HOST = "www.myconnectedsite.com"
DEFAULT_FTP_PORT = 21
DEFAULT_FTP_TIMEOUT = 60

MAX_UPLOAD_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024

DRY_RUN_BANNER = "DRY RUN — NO TCC CHANGES MADE"


def max_upload_bytes() -> int:
    raw = os.environ.get("MAX_UPLOAD_MB", "200").strip() or "200"
    try:
        megabytes = int(raw)
    except ValueError:
        megabytes = 200
    return max(1, megabytes) * 1024 * 1024
