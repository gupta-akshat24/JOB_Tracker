#!/usr/bin/env python3
"""CLI to update data/pipeline.json — your funnel status per job.

Usage:
    python scripts/track.py <job-id> <status> [--variant NAME] [--notes "text"]

Status must be one of: discovered, saved, applied, responded, interview,
offer, rejected. Run without arguments to list valid job ids from
data/jobs.json.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
JOBS_PATH = REPO_ROOT / "data" / "jobs.json"
PIPELINE_PATH = REPO_ROOT / "data" / "pipeline.json"

VALID_STATUSES = ["discovered", "saved", "applied", "responded", "interview", "offer", "rejected"]


def _load(path: pathlib.Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def _save(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def list_known_ids() -> list[str]:
    jobs = _load(JOBS_PATH, [])
    return [j["id"] for j in jobs if "id" in j]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_id", nargs="?", help="job id, e.g. greenhouse:acme:12345")
    parser.add_argument("status", nargs="?", choices=VALID_STATUSES, help="new pipeline status")
    parser.add_argument("--variant", help="resume variant used, e.g. business-analyst.docx")
    parser.add_argument("--notes", help="free-text note")
    args = parser.parse_args()

    if not args.job_id or not args.status:
        known = list_known_ids()
        print("Usage: python scripts/track.py <job-id> <status> [--variant NAME] [--notes TEXT]")
        print(f"Valid statuses: {', '.join(VALID_STATUSES)}")
        if known:
            print(f"\n{len(known)} known job ids (from data/jobs.json), most recent first:")
            for jid in known[:20]:
                print(f"  {jid}")
        return 1

    known = set(list_known_ids())
    if known and args.job_id not in known:
        print(f"warning: '{args.job_id}' isn't in data/jobs.json — tracking it anyway", file=sys.stderr)

    pipeline = _load(PIPELINE_PATH, {})
    entry = pipeline.get(args.job_id, {})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    entry["status"] = args.status
    if args.status == "applied" and "applied_at" not in entry:
        entry["applied_at"] = now
    if args.variant:
        entry["resume_variant"] = args.variant
    if args.notes:
        entry["notes"] = args.notes
    entry["updated_at"] = now
    entry.setdefault("discovered_at", entry.get("discovered_at", now))

    pipeline[args.job_id] = entry
    _save(PIPELINE_PATH, pipeline)

    print(f"{args.job_id} -> {args.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
