# Google Drive Storage

`data-forge` can store generated datasets, reports, review packets, and final exports in Google Drive. Git remains code-only.

## Setup

1. Create a Google Cloud project.
2. Enable the Google Drive API.
3. Create a service account.
4. Download the service-account JSON key.
5. Create a Google Drive folder named `data-forge`.
6. Share that folder with the service-account email as Editor.
7. Copy the Drive folder ID from the folder URL.

The folder URL looks like:

```text
https://drive.google.com/drive/folders/<folder-id>
```

## Local environment

```bash
export DEEPSEEK_API_KEY=...
export DATA_FORGE_STORAGE=gdrive
export DATA_FORGE_DRIVE_ROOT_ID=<folder-id>
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

Cloud agents can avoid writing a JSON key file by injecting:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON='<raw service account json>'
```

Never commit service-account JSON files.

## URI convention

Local:

```text
local://generation/niches/{niche}/runs/{run_id}
```

Google Drive:

```text
gdrive://niches/{niche}/runs/{run_id}
```

The Google Drive URI is resolved relative to `DATA_FORGE_DRIVE_ROOT_ID`.

## Standard run layout

```text
niches/{niche}/runs/{run_id}/
  raw/
  accepted/
  rejected/
  reports/
  review/
    decisions/
  reviewed/
  datasets/
  manifests/
```

## Review workflow

1. Generate and validate batches into Drive.
2. Build static HTML review packets.
3. Open the HTML packet locally or from a downloaded Drive file.
4. Approve, reject, or flag rows.
5. Export review decisions JSON from the browser.
6. Upload the decisions JSON into `review/decisions/`.
7. Apply review decisions.
8. Sign off the reviewed dataset.
9. Export the SFT dataset.

Fine-tuning export refuses to run without `signoff.json` unless `--unsafe-skip-review-signoff` is passed.
