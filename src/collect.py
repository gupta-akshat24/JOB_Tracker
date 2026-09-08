"""Entrypoint: python -m src.collect

Runs one full collection cycle:
  fetch (all sources) -> filter -> score -> notify -> store -> log to runs.json

Designed to run unattended on a 30-minute GitHub Actions cron. Never raises
out of the top-level `main()` — a total failure is caught, logged to
runs.json, and reported via a single capped Telegram alert instead of
crashing the workflow silently.
"""
from __future__ import annotations

import datetime
import sys
import traceback

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9 fallback, shouldn't happen in CI
    ZoneInfo = None

from . import store
from .config import load_config
from .filter import filter_jobs
from .score import score_jobs
from .notify import send_high_priority, send_digest, send_failure_alert
from .sources import greenhouse, lever, ashby, workable, smartrecruiters, rss

SOURCE_ADAPTERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workable": workable.fetch,
    "smartrecruiters": smartrecruiters.fetch,
}

DIGEST_HOUR_IST = 8  # send the digest during the first run at/after 08:00 IST


def _now_ist() -> datetime.datetime:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if ZoneInfo is not None:
        return now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    return now_utc + datetime.timedelta(hours=5, minutes=30)


def _fetch_all(config: dict) -> tuple[list[dict], dict]:
    """Returns (raw_jobs, source_stats). source_stats records per-source
    counts and failures for runs.json, per the spec's health-tracking
    requirement."""
    raw_jobs: list[dict] = []
    source_stats: dict[str, dict] = {}

    for company in config.get("companies", []):
        slug = company.get("slug")
        source_name = company.get("source")
        adapter = SOURCE_ADAPTERS.get(source_name)
        stat = source_stats.setdefault(
            source_name or "unknown", {"targets": 0, "jobs": 0, "failures": []}
        )
        stat["targets"] += 1
        if adapter is None:
            stat["failures"].append({"target": slug, "error": f"unknown source '{source_name}'"})
            continue
        try:
            jobs = adapter(slug, errors=stat["failures"])
        except Exception as e:  # adapters shouldn't raise, but never trust that fully
            jobs = []
            stat["failures"].append({"target": slug, "error": str(e)})
        stat["jobs"] += len(jobs)
        raw_jobs.extend(jobs)

    feed_stat = source_stats.setdefault("rss", {"targets": 0, "jobs": 0, "failures": []})
    for feed_url in config.get("feeds", []):
        feed_stat["targets"] += 1
        try:
            jobs = rss.fetch(feed_url, errors=feed_stat["failures"])
        except Exception as e:
            jobs = []
            feed_stat["failures"].append({"target": feed_url, "error": str(e)})
        feed_stat["jobs"] += len(jobs)
        raw_jobs.extend(jobs)

    return raw_jobs, source_stats


def _already_sent_today(runs: list[dict], key: str, today_ist: str) -> bool:
    for run in reversed(runs):
        if run.get("date_ist") != today_ist:
            continue
        if run.get(key):
            return True
    return False


def run_once() -> dict:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    now_ist = _now_ist()
    today_ist = now_ist.date().isoformat()

    config = load_config()
    store.ensure_data_files_exist()
    seen = store.load_seen()
    alerts_cfg = config.get("alerts", {})
    high_threshold = alerts_cfg.get("min_score_high_priority", 7)
    digest_threshold = alerts_cfg.get("min_score_digest", 5)

    raw_jobs, source_stats = _fetch_all(config)
    kept, filter_stats = filter_jobs(raw_jobs, config, seen)

    # Every raw job this run touched is now "seen" so we never re-filter or
    # re-fetch-score the same posting again, whether it matched or not.
    store.mark_seen_only([j["id"] for j in raw_jobs if j.get("id")])

    scored = score_jobs(kept) if kept else []

    if scored:
        store.save_new_matches(scored)

    high_priority = [j for j in scored if (j.get("score") or 0) >= high_threshold]
    digest_pending = [
        j for j in scored if digest_threshold <= (j.get("score") or 0) < high_threshold
    ]
    # Unscored jobs (score is None, e.g. the LLM call failed) must never be
    # silently dropped — route them into the digest so a human still sees them.
    digest_pending.extend(j for j in scored if j.get("score") is None)

    high_sent = send_high_priority(high_priority) if high_priority else 0
    for job in high_priority:
        job["notified_high_priority"] = True

    digest_sent = False
    runs_so_far = store.load_runs()
    is_digest_window = now_ist.hour == DIGEST_HOUR_IST and now_ist.minute < 30
    if is_digest_window and digest_pending and not _already_sent_today(
        runs_so_far, "digest_sent", today_ist
    ):
        digest_sent = send_digest(digest_pending)
        for job in digest_pending:
            job["notified_digest"] = True

    if high_priority or digest_sent:
        # Persist the notified flags we just set. save_new_matches already
        # wrote the fresh entries once above; this second pass updates the
        # notified_* flags now that we know the outcome of sending.
        all_jobs = store.load_jobs()
        by_id = {j["id"]: j for j in (high_priority + (digest_pending if digest_sent else []))}
        for job in all_jobs:
            update = by_id.get(job.get("id"))
            if update:
                job.update(update)
        store.overwrite_jobs(all_jobs)

    finished_at = datetime.datetime.now(datetime.timezone.utc)
    run_record = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "date_ist": today_ist,
        "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
        "status": "ok",
        "sources": source_stats,
        "filter": filter_stats,
        "scored": len(scored),
        "high_priority_sent": high_sent,
        "digest_sent": digest_sent,
        "digest_size": len(digest_pending) if digest_sent else 0,
    }
    store.append_run(run_record)
    return run_record


def main() -> int:
    try:
        record = run_once()
        print(
            f"[collect] ok — {record['filter']['input']} seen, "
            f"{record['filter']['kept']} matched, {record['scored']} scored, "
            f"{record['high_priority_sent']} pushed",
            file=sys.stderr,
        )
        return 0
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[collect] RUN FAILED: {e}\n{tb}", file=sys.stderr)
        today_ist = _now_ist().date().isoformat()
        try:
            runs = store.load_runs()
        except Exception:
            runs = []
        already_alerted = _already_sent_today(runs, "failure_alert_sent", today_ist)
        alert_sent = False
        if not already_alerted:
            alert_sent = send_failure_alert(str(e))
        try:
            store.append_run(
                {
                    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "date_ist": today_ist,
                    "status": "failed",
                    "error": str(e),
                    "failure_alert_sent": alert_sent,
                }
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
