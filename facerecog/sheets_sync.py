"""
Best-effort mirror of attendance events to a Google Sheet.

The local attendance.xlsx (attendance.py) remains the source of truth for
the gate/admin servers. This module pushes the same row to a Google Sheet
so the Vercel-hosted dashboard (which only ever reads the Sheet, never
your Mac) can show live/weekly reports without exposing anything else.

Configuration (env vars, both required to enable syncing — if either is
missing, sync_event() is a silent no-op so gate logging never breaks):
  GOOGLE_SHEET_ID              the spreadsheet ID (from its URL)
  GOOGLE_SERVICE_ACCOUNT_FILE  path to the service-account JSON key

Failures (network, quota, bad creds) are logged and swallowed — a Sheets
outage must never block a gate from recording attendance locally.
"""

import datetime
import os
import threading

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
SHEET_TAB = "Attendance"
HEADERS = ["Employee ID", "Name", "Date", "In Time", "Out Time"]

if SHEET_ID and CREDENTIALS_FILE:
    print(f"[sheets_sync] configured: sheet={SHEET_ID} creds={CREDENTIALS_FILE}")
else:
    print("[sheets_sync] not configured (GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_FILE missing) — local-only")

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_service = None
_service_lock = threading.Lock()
_init_failed = False


def _get_service():
    global _service, _init_failed

    if _service is not None or _init_failed:
        return _service

    if not (SHEET_ID and CREDENTIALS_FILE):
        return None

    with _service_lock:
        if _service is not None or _init_failed:
            return _service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = service_account.Credentials.from_service_account_file(
                CREDENTIALS_FILE, scopes=_SCOPES
            )
            _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            _ensure_header()
        except Exception as exc:
            print(f"[sheets_sync] disabled: could not init Sheets client: {exc}")
            _init_failed = True
            return None

        return _service


def _ensure_header():
    sheet = _service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!A1:E1"
    ).execute()
    if not result.get("values"):
        sheet.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A1:E1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()


def sync_event(employee_id, name, mode, when=None):
    """Fire-and-forget mirror of one attendance event to the Sheet."""
    service = _get_service()
    if service is None:
        return

    thread = threading.Thread(
        target=_sync_event_sync, args=(employee_id, name, mode, when), daemon=True
    )
    thread.start()


def _sync_event_sync(employee_id, name, mode, when):
    try:
        when = when or datetime.datetime.now()
        date_str = when.strftime("%Y-%m-%d")
        time_str = when.strftime("%H:%M:%S")

        sheet = _service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!A2:E"
        ).execute()
        rows = result.get("values", [])

        row_index = None
        for i, row in enumerate(rows):
            row = row + [""] * (5 - len(row))
            if row[0] == employee_id and row[2] == date_str:
                row_index = i
                existing = row
                break

        if row_index is None:
            new_row = [employee_id, name, date_str, "", ""]
            if mode == "in":
                new_row[3] = time_str
            else:
                new_row[4] = time_str
            sheet.values().append(
                spreadsheetId=SHEET_ID,
                range=f"{SHEET_TAB}!A2:E",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [new_row]},
            ).execute()
        else:
            sheet_row_num = row_index + 2  # +1 header, +1 for 1-indexing
            if mode == "in":
                if existing[3]:
                    return  # already has an in-time, don't overwrite
                cell_range = f"{SHEET_TAB}!D{sheet_row_num}"
            else:
                cell_range = f"{SHEET_TAB}!E{sheet_row_num}"
            sheet.values().update(
                spreadsheetId=SHEET_ID,
                range=cell_range,
                valueInputOption="RAW",
                body={"values": [[time_str]]},
            ).execute()
        print(f"[sheets_sync] synced {employee_id} ({mode}) at {time_str}")
    except Exception as exc:
        print(f"[sheets_sync] event sync failed (local record is unaffected): {exc}")
