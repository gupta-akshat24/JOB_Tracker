"""Greenhouse Job Board API adapter.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Public, no auth. `slug` is the company's Greenhouse board token (the part
after boards.greenhouse.io/ in their public jobs page URL).

Never raises: on any failure this logs to stderr and returns [].
"""
from __future__ import annotations

import sys

from ..http import get_json, log_failure, RateLimited
from ..textutil import html_to_text, truncate, looks_remote

SOURCE_NAME = "greenhouse"


def fetch(slug: str, errors: list | None = None) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        data = get_json(url)
    except RateLimited:
        log_failure(SOURCE_NAME, slug, "rate limited (429), skipping this run", errors)
        return []
    except Exception as e:
        log_failure(SOURCE_NAME, slug, f"fetch failed: {e}", errors)
        return []

    try:
        raw_jobs = data.get("jobs", [])
    except AttributeError:
        log_failure(SOURCE_NAME, slug, "unexpected response shape", errors)
        return []

    company_name = None
    if raw_jobs:
        company_name = raw_jobs[0].get("company_name")
    company_name = company_name or slug

    out = []
    for job in raw_jobs:
        try:
            out.append(_normalise(job, slug, company_name))
        except Exception as e:
            print(f"[greenhouse] {slug}: dropped one malformed job: {e}", file=sys.stderr)
    return out


def _normalise(job: dict, slug: str, company_name: str) -> dict:
    location = ""
    loc = job.get("location")
    if isinstance(loc, dict):
        location = loc.get("name") or ""
    elif isinstance(loc, str):
        location = loc

    description_html = job.get("content") or ""
    description = truncate(html_to_text(description_html))

    return {
        "id": f"greenhouse:{slug}:{job['id']}",
        "source": SOURCE_NAME,
        "company": company_name,
        "title": job.get("title") or "",
        "location": location,
        "remote": looks_remote(location, description),
        "url": job.get("absolute_url") or "",
        "posted_at": job.get("first_published") or job.get("updated_at"),
        "description": description,
    }


if __name__ == "__main__":
    # Milestone 1 smoke test: python -m src.sources.greenhouse <slug>
    import json

    slug = sys.argv[1] if len(sys.argv) > 1 else "gitlab"
    jobs = fetch(slug)
    print(f"# {len(jobs)} jobs from greenhouse/{slug}", file=sys.stderr)
    print(json.dumps(jobs, indent=2))
