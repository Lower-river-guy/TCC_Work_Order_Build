"""Build the default GCS master template from REV09 DK- folder names."""

from __future__ import annotations

import io
import zipfile

# Matches REV09 INPUT_FOLDER layout and RMV Testing Only standard work-order types.
TEMPLATE_FOLDER_SUFFIXES = (
    "Asbuilt",
    "Check In",
    "Corrections",
    "Existing Utilities",
    "Geology",
    "Junk",
    "Key Btms",
    "Pad ox",
    "Pothole",
    "Quanties",
    "Removal Area",
    "Removal Btms",
    "Stakeout",
    "Subdrain",
    "Subdrain markers",
    "Survey Capture",
    "Topo",
    "Wall Drains",
)


def build_master_template_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for suffix in TEMPLATE_FOLDER_SUFFIXES:
            folder = f"DK-{suffix}"
            archive.writestr(f"{folder}/", b"")
            archive.writestr(f"{folder}/notes.txt", b"template")
    return buffer.getvalue()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from app.builder import build_work_orders, validate_work_order_template_root
    from app.template_source import prepare_template_root

    payload = build_master_template_zip()
    with __import__("tempfile").TemporaryDirectory() as temp_name:
        root = prepare_template_root(payload, Path(temp_name))
        validate_work_order_template_root(root)
        _built, report = build_work_orders(root, "DK-", "RK-")
        print(f"work_orders={len(report.work_orders)}")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Work Orders.zip")
    out.write_bytes(payload)
    print(f"wrote {out} ({len(payload)} bytes)")
