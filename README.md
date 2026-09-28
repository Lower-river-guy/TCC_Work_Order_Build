# TCC Work Order Builder

Version 0.01.04

Web application for TCC work-order uploads. The server loads the **default** master template from Google Cloud Storage or a **custom** ZIP uploaded for a single operation. Folder names in the template use `DK-`; the app replaces `DK-` with the **Work Order Prefix** you enter (default `RK-`).

Master template (default):

`gs://trimble-data-bucket-rk/tcc-work-order-builder/templates/Work Orders.zip`

Custom ZIPs are processed under a unique temporary directory and are never written to GCS.

## Workflow

1. **Template** — keep **Use Default Work Order Template** checked, or upload a custom `.zip`.
2. **Work Order Prefix** — default `RK-` (examples: `MH-`, `KL-`, `JS-`).
3. **Device** and **Project** on TCC FTP.
4. **Dry Run** (default on) — preview with no FTP writes.
5. **Preview** / **Run Dry Run** / **Upload New Work Orders** (with confirmation when not dry run).

## Local run

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
python -m app.main
```

## Environment

| Name | Purpose |
| --- | --- |
| `TCC_T48_DEVICE_USER` / `TCC_T48_DEVICE_PASS` | T48 FTP login (Secret Manager on Cloud Run). |
| `GCS_TEMPLATE_BUCKET` / `GCS_TEMPLATE_OBJECT` | Default master template location. |
| `MAX_UPLOAD_MB` | Custom template upload limit (default `200`). |
| `APP_ACCESS_TOKEN` | Optional access control. |
