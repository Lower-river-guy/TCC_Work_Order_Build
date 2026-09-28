"""Load the master Work Orders template from Google Cloud Storage."""

from __future__ import annotations

import os

from app.settings import GCS_TEMPLATE_BUCKET, GCS_TEMPLATE_OBJECT


def fetch_master_template_bytes() -> bytes:
    """Download the master template ZIP from GCS."""
    bucket_name = os.environ.get("GCS_TEMPLATE_BUCKET", GCS_TEMPLATE_BUCKET).strip() or GCS_TEMPLATE_BUCKET
    object_name = os.environ.get("GCS_TEMPLATE_OBJECT", GCS_TEMPLATE_OBJECT).strip() or GCS_TEMPLATE_OBJECT
    client = _storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(
            f"Master template was not found at gs://{bucket_name}/{object_name}"
        )
    data = blob.download_as_bytes()
    if not data:
        raise ValueError("Master template object is empty.")
    return data


def _storage_client():
    from google.cloud import storage

    return storage.Client()
