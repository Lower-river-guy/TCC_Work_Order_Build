# TCC Work Order Builder

Version 0.01.00

Web application for the REV09 work-order build. Upload a ZIP of template folders, rename folder names (default `DK-` to `CL-`), add placeholder files and `Output` folders, then download `Work Orders.zip`.

When FTP credentials are configured, the same ZIP can be sent to TCC. The T48 login only opens the server. The device and project are chosen in the page. Existing remote work orders are skipped. Dry run is the default and does not create folders or upload files.

Production Cloud Run deployment is waiting for approval. This repository is the source only.

## What the build does

- Each top-level folder in the template becomes one work order.
- Folder names are replaced without regard to case. A folder named `Output` stays exactly `Output`.
- A non-Output folder with no file matching its own name gets a placeholder file named after the folder. The placeholder contains `11` and a Windows newline.
- An existing file that matches its parent folder name is renamed to the new folder name.
- Every non-Output folder gets an `Output` subfolder.
- Other files are copied.
- If two folders would share a name after renaming, the later one gets `_2`, `_3`, and so on.

A ZIP whose only top-level folder contains other folders and no files is treated as a wrapper and unwrapped. A single work order that already contains files is kept as that work order.

## Local run

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
python -m app.main
```

Open `http://127.0.0.1:8080`.

## Environment

Copy `.env.example` to `.env` for local experiments. Do not commit `.env`.

| Name | Purpose |
| --- | --- |
| `APP_ACCESS_TOKEN` | Optional. When set, pages and API routes require this token. `/health` and `/api/config` stay open. |
| `TCC_T48_DEVICE_USER` | FTP username |
| `TCC_T48_DEVICE_PASS` | FTP password |
| `TCC_FTP_HOST` | Default `www.myconnectedsite.com` |
| `TCC_FTP_PORT` | Default `21` |
| `TCC_FTP_TIMEOUT` | Default `60` seconds |
| `TCC_DEVICE_ENV_FILE` | Optional local `KEY=VALUE` file used only when the two T48 variables are unset |
| `MAX_UPLOAD_MB` | Default `200` |
| `PORT` | Default `8080` |

Cloud Run should receive the T48 values from Secret Manager. The image does not contain passwords.

## Tests

```powershell
python -m unittest discover -s tests -t . -v
```

FTP tests use an in-memory server. They do not connect to TCC.

## Cloud Run later

Do not deploy until production deployment is explicitly approved.

The container listens on `$PORT` and starts `gunicorn` with `app.main:app`. A later deploy can map `TCC_T48_DEVICE_USER` and `TCC_T48_DEVICE_PASS` from Secret Manager and set `APP_ACCESS_TOKEN`. Restrict the service so it is not anonymously public.
