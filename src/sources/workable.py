"""Workable widget API adapter.

Endpoint: https://apply.workable.com/api/v1/widget/accounts/{slug}
Public, no auth. `slug` is the company's Workable account name (the part
after apply.workable.com/ in their public jobs page URL).

The widget endpoint's job list doesn't carry a full description — only a
title/department/location summary — so `description` here is whatever
summary text the widget gives us. That's enough for the experience-band
regex to mostly come up empty (flagged experience_stated: false) rather
than wrong, which is the safer failure mode.

Never raises: on any failure this logs to stderr and returns [].
"""
from __future__ import annotations

import sys

from ..http import get_json, log_failure, RateLimited
from ..textutil import truncate, looks_remote

SOURCE_NAME = "workable"


def fetch(slug: str, errors: list | None = None) -> list[dict]:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    try:
        data = get_json(url)
    except RateLimited:
        log_failure(SOURCE_NAME, slug, "rate limited (429), skipping this run", errors)
        return []
    except Exception as e:
        log_failure(SOURCE_NAME, slug, f"fetch failed: {e}", errors)
        return []

    raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
    company_name = (data.get("name") if isinstance(data, dict) else None) or slug

    out = []
    for job in raw_jobs:
        try:
            out.append(_normalise(job, slug, company_name))
        except Exception as e:
            print(f"[workable] {slug}: dropped one malformed job: {e}", file=sys.stderr)
    return out


def _normalise(job: dict, slug: str, company_name: str) -> dict:
    loc = job.get("location") or {}
    location_bits = [loc.get("city"), loc.get("region"), loc.get("country")]
    location = ", ".join(b for b in location_bits if b)

    telecommuting = job.get("telecommuting")
    description_bits = [job.get("department"), job.get("employment_type")]
    description = truncate(" · ".join(b for b in description_bits if b))

    shortcode = job.get("shortcode") or job.get("code") or job.get("id")

    return {
        "id": f"workable:{slug}:{shortcode}",
        "source": SOURCE_NAME,
        "company": company_name,
        "title": job.get("title") or "",
        "location": location,
        "remote": telecommuting if isinstance(telecommuting, bool) else looks_remote(location),
        "url": job.get("url") or "",
        "posted_at": job.get("published_on"),
        "description": description,
    }


if __name__ == "__main__":
    import json

    slug = sys.argv[1] if len(sys.argv) > 1 else "example"
    jobs = fetch(slug)
    print(f"# {len(jobs)} jobs from workable/{slug}", file=sys.stderr)
    print(json.dumps(jobs, indent=2))
