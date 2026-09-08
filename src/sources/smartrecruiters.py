"""SmartRecruiters Posting API adapter.

List endpoint:   https://api.smartrecruiters.com/v1/companies/{slug}/postings
Detail endpoint: https://api.smartrecruiters.com/v1/companies/{slug}/postings/{id}
Public, no auth. `slug` is the company's SmartRecruiters identifier.

The list endpoint doesn't carry a job description, only title/location, so
we fetch each posting's detail too (still through the shared rate limiter,
so a company with many open roles takes proportionally longer — that's
fine on a 30-minute cron).

Never raises: on any failure this logs to stderr and returns [].
"""
from __future__ import annotations

import sys

from ..http import get_json, log_failure, RateLimited
from ..textutil import html_to_text, truncate, looks_remote

SOURCE_NAME = "smartrecruiters"


def fetch(slug: str, errors: list | None = None) -> list[dict]:
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    try:
        data = get_json(url)
    except RateLimited:
        log_failure(SOURCE_NAME, slug, "rate limited (429), skipping this run", errors)
        return []
    except Exception as e:
        log_failure(SOURCE_NAME, slug, f"fetch failed: {e}", errors)
        return []

    raw_jobs = data.get("content", []) if isinstance(data, dict) else []

    out = []
    for job in raw_jobs:
        try:
            out.append(_normalise(job, slug))
        except RateLimited:
            log_failure(SOURCE_NAME, slug, "rate limited mid-run, stopping early", errors)
            break
        except Exception as e:
            print(f"[smartrecruiters] {slug}: dropped one malformed job: {e}", file=sys.stderr)
    return out


def _fetch_detail(slug: str, posting_id: str) -> dict:
    detail_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"
    try:
        return get_json(detail_url) or {}
    except Exception as e:
        print(f"[smartrecruiters] {slug}/{posting_id}: detail fetch failed: {e}", file=sys.stderr)
        return {}


def _normalise(job: dict, slug: str) -> dict:
    loc = job.get("location") or {}
    location_bits = [loc.get("city"), loc.get("region"), loc.get("country")]
    location = ", ".join(b for b in location_bits if b)
    remote = loc.get("remote")

    company = (job.get("company") or {}).get("name") or slug
    posting_id = job.get("id")

    detail = _fetch_detail(slug, posting_id) if posting_id else {}
    sections = detail.get("jobAd", {}).get("sections", {}) if isinstance(detail, dict) else {}
    parts = [s.get("text") or "" for s in sections.values() if isinstance(s, dict)]
    description = truncate(html_to_text("\n".join(parts)))
    url = detail.get("postingUrl") or detail.get("applyUrl") or job.get("applyUrl") or ""

    return {
        "id": f"smartrecruiters:{slug}:{posting_id}",
        "source": SOURCE_NAME,
        "company": company,
        "title": job.get("name") or "",
        "location": location,
        "remote": remote if isinstance(remote, bool) else looks_remote(location, description),
        "url": url,
        "posted_at": job.get("releasedDate"),
        "description": description,
    }


if __name__ == "__main__":
    import json

    slug = sys.argv[1] if len(sys.argv) > 1 else "example"
    jobs = fetch(slug)
    print(f"# {len(jobs)} jobs from smartrecruiters/{slug}", file=sys.stderr)
    print(json.dumps(jobs, indent=2))
