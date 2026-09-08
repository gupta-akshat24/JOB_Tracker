"""Shared HTTP helper: rate limiting, a real User-Agent, and 429 backoff.

All source adapters go through `get_json` / `get_text` so the whole
collector obeys a single global rate limit (max 1 request/second) no
matter how many sources or companies are configured.
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
import json as _json

CONTACT_EMAIL = "bluegold2001@gmail.com"
USER_AGENT = f"job-radar/1.0 (+contact: {CONTACT_EMAIL})"

MIN_INTERVAL_SECONDS = 1.0
_last_request_at = 0.0


class RateLimited(Exception):
    """Raised when a source returns 429. Callers should back off and skip."""


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def get_text(url: str, timeout: int = 20) -> str:
    """Fetch a URL as text, honoring the global rate limit.

    Raises RateLimited on HTTP 429, and urllib.error.HTTPError/URLError on
    any other failure. Callers are responsible for catching and logging.
    """
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(str(url)) from e
        raise


def get_json(url: str, timeout: int = 20):
    return _json.loads(get_text(url, timeout=timeout))


def log_failure(source: str, target: str, message: str, errors: list | None = None) -> None:
    """Print to stderr and, if the caller passed a list, also append a
    structured record so collect.py can surface it in runs.json for the
    dashboard's System Health view."""
    print(f"[{source}] {target}: {message}", file=sys.stderr)
    if errors is not None:
        errors.append({"target": target, "error": message})
