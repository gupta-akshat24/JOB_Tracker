"""Generic RSS/Atom feed adapter — for Google Alerts feeds and any other feed URL.

Uses Python's stdlib xml.etree so we don't need a pinned feedparser dep.
Handles both RSS 2.0 (<item>) and Atom (<entry>) shapes loosely.

Never raises: on any failure this logs to stderr and returns [].
"""
from __future__ import annotations

import hashlib
import sys
import xml.etree.ElementTree as ET

from ..http import get_text, log_failure, RateLimited
from ..textutil import html_to_text, truncate, looks_remote

SOURCE_NAME = "rss"

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch(feed_url: str, errors: list | None = None) -> list[dict]:
    try:
        body = get_text(feed_url)
    except RateLimited:
        log_failure(SOURCE_NAME, feed_url, "rate limited (429), skipping this run", errors)
        return []
    except Exception as e:
        log_failure(SOURCE_NAME, feed_url, f"fetch failed: {e}", errors)
        return []

    try:
        root = ET.fromstring(body)
    except Exception as e:
        log_failure(SOURCE_NAME, feed_url, f"XML parse failed: {e}", errors)
        return []

    items = root.findall(".//item")
    if items:
        parse_one = _parse_rss_item
    else:
        items = root.findall(".//atom:entry", _ATOM_NS)
        parse_one = _parse_atom_entry

    out = []
    for item in items:
        try:
            job = parse_one(item, feed_url)
            if job:
                out.append(job)
        except Exception as e:
            print(f"[rss] {feed_url}: dropped one malformed entry: {e}", file=sys.stderr)
    return out


def _stable_id(feed_url: str, link: str, title: str) -> str:
    key = f"{feed_url}|{link}|{title}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"rss:{digest}"


def _parse_rss_item(item, feed_url: str) -> dict | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    if not title and not link:
        return None
    description = truncate(html_to_text(item.findtext("description") or ""))
    posted_at = item.findtext("pubDate")

    return {
        "id": _stable_id(feed_url, link, title),
        "source": SOURCE_NAME,
        "company": "",  # unknown from a bare feed; filter/score work off title+description
        "title": title,
        "location": "",
        "remote": looks_remote(title, description),
        "url": link,
        "posted_at": posted_at,
        "description": description,
    }


def _parse_atom_entry(entry, feed_url: str) -> dict | None:
    title = (entry.findtext("atom:title", namespaces=_ATOM_NS) or "").strip()
    link_el = entry.find("atom:link", _ATOM_NS)
    link = link_el.get("href") if link_el is not None else ""
    if not title and not link:
        return None
    summary = entry.findtext("atom:summary", namespaces=_ATOM_NS) or entry.findtext(
        "atom:content", namespaces=_ATOM_NS
    )
    description = truncate(html_to_text(summary or ""))
    posted_at = entry.findtext("atom:published", namespaces=_ATOM_NS) or entry.findtext(
        "atom:updated", namespaces=_ATOM_NS
    )

    return {
        "id": _stable_id(feed_url, link, title),
        "source": SOURCE_NAME,
        "company": "",
        "title": title,
        "location": "",
        "remote": looks_remote(title, description),
        "url": link or "",
        "posted_at": posted_at,
        "description": description,
    }


if __name__ == "__main__":
    import json

    feed_url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not feed_url:
        print("usage: python -m src.sources.rss <feed-url>", file=sys.stderr)
        sys.exit(1)
    jobs = fetch(feed_url)
    print(f"# {len(jobs)} entries from {feed_url}", file=sys.stderr)
    print(json.dumps(jobs, indent=2))
