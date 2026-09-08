"""Ashby Job Board API adapter.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}
Public, no auth. `slug` is the company's Ashby job board name (the part
after jobs.ashbyhq.com/ in their public postings page URL).

Never raises: on any failure this logs to stderr and returns [].
"""
from __future__ import annotations

import sys

from ..http import get_json, log_failure, RateLimited
from ..textutil import html_to_text, truncate, looks_remote

SOURCE_NAME = "ashby"


def fetch(slug: str, errors: list | None = None) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        data = get_json(url)
    except RateLimited:
        log_failure(SOURCE_NAME, slug, "rate limited (429), skipping this run", errors)
        return []
    except Exception as e:
        log_failure(SOURCE_NAME, slug, f"fetch failed: {e}", errors)
        return []

    raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []

    out = []
    for job in raw_jobs:
        try:
            out.append(_normalise(job, slug))
        except Exception as e:
            print(f"[ashby] {slug}: dropped one malformed job: {e}", file=sys.stderr)
    return out


def _normalise(job: dict, slug: str) -> dict:
    location = job.get("location") or ""
    is_remote = job.get("isRemote")
    description = truncate(html_to_text(job.get("descriptionHtml") or job.get("description")))

    return {
        "id": f"ashby:{slug}:{job['id']}",
        "source": SOURCE_NAME,
        "company": slug,
        "title": job.get("title") or "",
        "location": location,
        "remote": is_remote if isinstance(is_remote, bool) else looks_remote(location, description),
        "url": job.get("jobUrl") or job.get("applyUrl") or "",
        "posted_at": job.get("publishedAt") or job.get("publishedDate"),
        "description": description,
    }


if __name__ == "__main__":
    import json

    slug = sys.argv[1] if len(sys.argv) > 1 else "rippling"
    jobs = fetch(slug)
    print(f"# {len(jobs)} jobs from ashby/{slug}", file=sys.stderr)
    print(json.dumps(jobs, indent=2))
