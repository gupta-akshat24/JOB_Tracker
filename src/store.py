"""Dedupe against seen.json and persist results to data/*.json.

All writes are atomic (write to a temp file, then rename) so a crash
mid-run never leaves a corrupt JSON file for the dashboard to choke on.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib

from .config import DATA_DIR

JOBS_PATH = DATA_DIR / "jobs.json"
SEEN_PATH = DATA_DIR / "seen.json"
RUNS_PATH = DATA_DIR / "runs.json"

MAX_RUNS_KEPT = 500


def _read_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json_atomic(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, path)


def load_seen() -> set[str]:
    data = _read_json(SEEN_PATH, [])
    if isinstance(data, list):
        return set(data)
    return set()


def load_jobs() -> list[dict]:
    data = _read_json(JOBS_PATH, [])
    return data if isinstance(data, list) else []


def load_runs() -> list[dict]:
    data = _read_json(RUNS_PATH, [])
    return data if isinstance(data, list) else []


def save_new_matches(new_jobs: list[dict]) -> list[dict]:
    """Prepend new_jobs (already filtered+scored) to jobs.json, newest first.

    Also merges their ids into seen.json. Returns the full updated jobs list.
    """
    existing = load_jobs()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for job in new_jobs:
        job.setdefault("discovered_at", now)

    all_jobs = new_jobs + existing
    _write_json_atomic(JOBS_PATH, all_jobs)

    seen = load_seen()
    seen.update(job["id"] for job in new_jobs if job.get("id"))
    _write_json_atomic(SEEN_PATH, sorted(seen))

    return all_jobs


def overwrite_jobs(all_jobs: list[dict]) -> None:
    """Full rewrite of jobs.json (e.g. after flipping notified_* flags)."""
    _write_json_atomic(JOBS_PATH, all_jobs)


def mark_seen_only(job_ids: list[str]) -> None:
    """Record ids as seen without adding them to jobs.json (e.g. filtered-out
    jobs still shouldn't be re-fetched/re-scored on every run)."""
    seen = load_seen()
    seen.update(j for j in job_ids if j)
    _write_json_atomic(SEEN_PATH, sorted(seen))


def append_run(run_record: dict) -> None:
    runs = load_runs()
    runs.append(run_record)
    if len(runs) > MAX_RUNS_KEPT:
        runs = runs[-MAX_RUNS_KEPT:]
    _write_json_atomic(RUNS_PATH, runs)


def ensure_data_files_exist() -> None:
    for path, default in ((JOBS_PATH, []), (SEEN_PATH, []), (RUNS_PATH, [])):
        if not path.exists():
            _write_json_atomic(path, default)
