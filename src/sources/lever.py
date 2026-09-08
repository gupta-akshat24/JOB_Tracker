"""Lever Postings API adapter.

Endpoint: https://api.lever.co/v0/postings/{slug}?mode=json
Public, no auth. `slug` is the company's Lever site token (the part after
jobs.lever.co/ in their public postings page URL).

Never raises: on any failure this logs to stderr and returns [].
"""
from __future__ import annotations

import sys

from ..http import get_json, log_failure, RateLimited
from ..textutil import html_to_text, truncate, looks_remote

SOURCE_NAME = "lever"


def fetch(slug: str, errors: list | None = None) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        data = get_json(url)
    except RateLimited:
        log_failure(SOURCE_NAME, slug, "rate limited (429), skipping this run", errors)
        return []
    except Exception as e:
        log_failure(SOURCE_NAME, slug, f"fetch failed: {e}", errors)
        return []

    if not isinstance(data, list):
        log_failure(SOURCE_NAME, slug, "unexpected response shape", errors)
        return []

    out = []
    for job in data:
        try:
            out.append(_normalise(job, slug))
        except Exception as e:
            print(f"[lever] {slug}: dropped one malformed job: {e}", file=sys.stderr)
    return out


def _normalise(job: dict, slug: str) -> dict:
    categories = job.get("categories") or {}
    location = categories.get("location") or ""
    commitment = categories.get("commitment") or ""

    lists = job.get("lists") or []
    description_parts = [job.get("descriptionPlain") or html_to_text(job.get("description"))]
    for section in lists:
        text = section.get("text") or ""
        content = section.get("content") or ""
        description_parts.append(f"{text}\n{html_to_text(content)}")
    description = truncate("\n\n".join(p for p in description_parts if p))

    posted_at = None
    created_at = job.get("createdAt")
    if isinstance(created_at, (int, float)):
        import datetime

        posted_at = datetime.datetime.utcfromtimestamp(created_at / 1000).date().isoformat()

    return {
        "id": f"lever:{slug}:{job['id']}",
        "source": SOURCE_NAME,
        "company": slug,
        "title": job.get("text") or "",
        "location": location,
        "remote": looks_remote(location, commitment, description),
        "url": job.get("hostedUrl") or job.get("applyUrl") or "",
        "posted_at": posted_at,
        "description": description,
    }


if __name__ == "__main__":
    import json

    slug = sys.argv[1] if len(sys.argv) > 1 else "netflix"
    jobs = fetch(slug)
    print(f"# {len(jobs)} jobs from lever/{slug}", file=sys.stderr)
    print(json.dumps(jobs, indent=2))
