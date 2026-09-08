#!/usr/bin/env python3
"""Optional: sync data/pipeline.json with a Google Sheet so you can update
your funnel status from your phone.

Strictly optional. The whole system works with no Sheets setup at all —
just edit data/pipeline.json by hand or use scripts/track.py. This only
does anything if:
  1. `gspread` and `google-auth` are installed (they're in requirements.txt
     but nothing else in the system imports them), and
  2. the GOOGLE_SERVICE_ACCOUNT_JSON and PIPELINE_SHEET_ID env vars are set.

Sheet layout expected (one row per job, header row required):
    job_id | status | applied_at | resume_variant | notes

Usage:
    python scripts/sheets_sync.py pull   # sheet -> data/pipeline.json
    python scripts/sheets_sync.py push   # data/pipeline.json -> sheet

Run `pull` at the start of collect.py's workflow step (before the collector
reads pipeline.json) if you want phone edits to flow back in automatically;
see README.md.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINE_PATH = REPO_ROOT / "data" / "pipeline.json"

HEADER = ["job_id", "status", "applied_at", "resume_variant", "notes"]


def _get_worksheet():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print(
            "sheets_sync: gspread/google-auth not installed — "
            "`pip install -r requirements.txt` if you want Sheets sync.",
            file=sys.stderr,
        )
        return None

    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.environ.get("PIPELINE_SHEET_ID")
    if not creds_json or not sheet_id:
        print(
            "sheets_sync: GOOGLE_SERVICE_ACCOUNT_JSON or PIPELINE_SHEET_ID not set — "
            "Sheets sync is optional and disabled, skipping.",
            file=sys.stderr,
        )
        return None

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    return sheet.sheet1


def _load_pipeline() -> dict:
    if not PIPELINE_PATH.exists():
        return {}
    with open(PIPELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_pipeline(pipeline: dict) -> None:
    PIPELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PIPELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(pipeline, f, indent=2, ensure_ascii=False)
        f.write("\n")


def pull() -> int:
    ws = _get_worksheet()
    if ws is None:
        return 0  # optional feature disabled; not an error
    rows = ws.get_all_records()
    pipeline = _load_pipeline()
    for row in rows:
        job_id = row.get("job_id")
        if not job_id:
            continue
        entry = pipeline.get(job_id, {})
        for key in ("status", "applied_at", "resume_variant", "notes"):
            if row.get(key):
                entry[key] = row[key]
        pipeline[job_id] = entry
    _save_pipeline(pipeline)
    print(f"sheets_sync: pulled {len(rows)} rows into pipeline.json")
    return 0


def push() -> int:
    ws = _get_worksheet()
    if ws is None:
        return 0
    pipeline = _load_pipeline()
    rows = [HEADER]
    for job_id, entry in pipeline.items():
        rows.append(
            [
                job_id,
                entry.get("status", ""),
                entry.get("applied_at", ""),
                entry.get("resume_variant", ""),
                entry.get("notes", ""),
            ]
        )
    ws.clear()
    ws.update(rows)
    print(f"sheets_sync: pushed {len(rows) - 1} rows to the sheet")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("pull", "push"):
        print(__doc__)
        return 1
    return pull() if sys.argv[1] == "pull" else push()


if __name__ == "__main__":
    sys.exit(main())
