# Google Sheets setup (Fabio bot)

This checklist matches the environment variables used by [`frontend/sheets_logger.py`](../frontend/sheets_logger.py) and related tooling.

## 1. Create a Google Cloud project

1. In [Google Cloud Console](https://console.cloud.google.com/), create or select a project.
2. Enable the **Google Sheets API** for that project.

## 2. Service account and key

1. Create a **service account** (IAM → Service Accounts).
2. Create a **JSON key** for the service account and download it.
3. Store the JSON **outside** this repository (or anywhere covered by `.gitignore`). Never commit the key file.
4. Set in your `.env` (see [`portal/.env.example`](../portal/.env.example)):

   - `GOOGLE_CREDS_PATH` — absolute path to the JSON key file.
   - `GOOGLE_SHEET_ID` — the spreadsheet ID from the sheet URL (`docs.google.com/spreadsheets/d/<ID>/...`).

## 3. Share the spreadsheet

Open your Google Sheet → **Share** → add the service account **email** (from the JSON, `client_email`) with **Editor** access so the bot can write tabs.

## 4. Verify

With `PYTHONPATH=backend:frontend` and `.env` loaded from the Fabio repo root, run the bot or a small script that imports `sheets_logger` and confirms `gspread` can open the workbook.

If Sheets logging is optional on your machine, you can skip installing `gspread` until you need live logging.
