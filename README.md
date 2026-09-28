# TCC Work Order Builder

Version 0.01.01

Web application for TCC work-order uploads. The server loads the master template from Google Cloud Storage, applies the selected grade-checker prefix, compares the result against the project's `Work Orders` folder on TCC FTP, and uploads only new top-level work orders.

Master template:

`gs://trimble-data-bucket-rk/tcc-work-order-builder/templates/Work Orders.zip`

Users do not upload or download template ZIP files in the website.

## Workflow

1. Choose **Grade Checker** (Ryan Kolt → `RK-` from master `DK-` names).
2. Choose **Device** and **Project** on TCC FTP.
3. Leave **Dry Run** checked to preview with no FTP writes, or uncheck it to upload after confirmation.
4. Run **Preview** or **Run Dry Run** / **Upload New Work Orders**.

Dry run defaults to on for every page load and is not stored in browser storage.

## Local run

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
python -m app.main
```

## Environment

| Name | Purpose |
| --- | --- |
| `APP_ACCESS_TOKEN` | Optional access token for pages and API routes except `/health` and `/api/config`. |
| `TCC_T48_DEVICE_USER` / `TCC_T48_DEVICE_PASS` | T48 FTP login (Secret Manager on Cloud Run). |
| `GCS_TEMPLATE_BUCKET` | Default `trimble-data-bucket-rk`. |
| `GCS_TEMPLATE_OBJECT` | Default `tcc-work-order-builder/templates/Work Orders.zip`. |
| `TCC_FTP_HOST`, `TCC_FTP_PORT`, `TCC_FTP_TIMEOUT` | FTP connection settings. |
| `TCC_DEVICE_ENV_FILE` | Optional local env file when T48 variables are unset. |

Cloud Run deployment requires permission to read the master template object. Production deploy is separate from this repository revision.
