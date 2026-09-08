"""Telegram notifications.

- score >= min_score_high_priority: push immediately, one message per job.
- min_score_digest <= score < min_score_high_priority: held for a single
  grouped digest (send_digest, meant to be called once/day by a separate
  cron entry or by collect.py when it's the right time of day).
- score < min_score_digest (or None and low-signal): dashboard only.
- Never send the same job twice — callers should only pass genuinely new
  matches; notify.py itself keeps no additional state.
- If a run produces nothing, send nothing. Silence means "nothing new".
- send_failure_alert is capped to once/day by the caller (collect.py),
  using data/runs.json to check whether one already went out today.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

TELEGRAM_API_BASE = "https://api.telegram.org"


def _send_message(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notify] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; skipping send", file=sys.stderr)
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    body = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[notify] Telegram send failed: {e}", file=sys.stderr)
        return False


def _format_job(job: dict) -> str:
    score = job.get("score")
    score_label = f"[{score}]" if score is not None else "[?]"
    title = job.get("title", "")
    company = job.get("company", "")
    location = job.get("location", "") or "location n/a"
    band = (
        f"up to {job['min_years_required']:.0f} yrs"
        if job.get("min_years_required") is not None
        else "yrs n/a"
    )
    source = job.get("source", "")
    why = job.get("why") or "—"
    gap = job.get("gap") or "—"
    variant = job.get("resume_variant") or "—"
    url = job.get("url", "")

    return (
        f"{score_label} {job.get('track', '')} — {company}\n"
        f"{title}\n"
        f"{location} · {band} · {source}\n"
        f"Why: {why}\n"
        f"Gap: {gap}\n"
        f"Use: {variant}\n"
        f"{url}"
    )


def send_high_priority(jobs: list[dict]) -> int:
    """One message per job. Returns how many were actually sent."""
    sent = 0
    for job in jobs:
        if _send_message(_format_job(job)):
            sent += 1
    return sent


def send_digest(jobs: list[dict]) -> bool:
    """One grouped message for everything between the digest and
    high-priority thresholds. No-op (returns False) if jobs is empty."""
    if not jobs:
        return False
    lines = [f"Daily digest — {len(jobs)} new match{'es' if len(jobs) != 1 else ''}", ""]
    for job in jobs:
        lines.append(_format_job(job))
        lines.append("")
    return _send_message("\n".join(lines).strip())


def send_failure_alert(message: str) -> bool:
    return _send_message(f"⚠️ Job Radar run failed: {message}")
