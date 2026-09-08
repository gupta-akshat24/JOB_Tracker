# Job Radar

A self-hosted job alert system. Runs on GitHub Actions every 30 minutes, pulls
open roles from company ATS boards and RSS feeds, filters out anything
outside your experience band or target roles, scores what survives with an
LLM, pushes new matches to Telegram, and appends them to a dashboard on
GitHub Pages. Total cost: zero.

## ⚠️ Before you rely on this: verify the source endpoints

This project was built in a sandboxed environment with no outbound network
access, so the ATS endpoint patterns in `config.yaml` and `src/sources/*.py`
could **not** be verified against live traffic while building. They follow
each vendor's long-standing, documented public API shape (see the table
below), and every adapter is written to fail safely — a 404 or shape change
logs to `data/runs.json` and returns no jobs, it never crashes the run — but
you should not trust a scaffolded company slug until you've seen it work.

The very first time `collect.yml` runs on GitHub Actions (which has normal
internet access), check the **System Health** tab of the dashboard. Any
source with a red "failing" line is either a wrong slug or a pattern that's
drifted — fix or drop it per the debugging steps below.

| Source | Pattern | Slug is... |
|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | the token in `boards.greenhouse.io/{slug}` |
| Lever | `https://api.lever.co/v0/postings/{slug}?mode=json` | the token in `jobs.lever.co/{slug}` |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{slug}` | the token in `jobs.ashbyhq.com/{slug}` |
| Workable | `https://apply.workable.com/api/v1/widget/accounts/{slug}` | the token in `apply.workable.com/{slug}` |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{slug}/postings` | the company identifier SmartRecruiters assigned them |
| RSS | any feed URL | — |

The 5 companies scaffolded in `config.yaml` are a starting point, not a
verified list — treat them the same way.

## What you get

- `src/collect.py` — the entrypoint. Fetches every source, filters
  deterministically, scores survivors with an LLM, sends Telegram alerts,
  writes everything to `data/`.
- `.github/workflows/collect.yml` — runs `collect.py` every 30 minutes and
  commits the updated `data/` files back to the repo.
- `docs/` — a static dashboard (GitHub Pages) with four views: Feed, Where
  the jobs are, My funnel, System health.
- `scripts/track.py` — a CLI to record your application status per job.
- `scripts/sheets_sync.py` — optional Google Sheets sync for the same, so
  you can update status from your phone.

## Setup

### 1. Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository
secret**. All are optional except you'll want at least one LLM key and the
two Telegram ones for alerts to actually reach you.

| Secret | Required for | How to get it |
|---|---|---|
| `GEMINI_API_KEY` | LLM scoring (primary) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — free tier |
| `GROQ_API_KEY` | LLM scoring (fallback if Gemini key missing/failing) | [console.groq.com/keys](https://console.groq.com/keys) — free tier |
| `TELEGRAM_BOT_TOKEN` | Telegram push | message [@BotFather](https://t.me/BotFather), `/newbot` |
| `TELEGRAM_CHAT_ID` | Telegram push | message your new bot, then open `https://api.telegram.org/bot<token>/getUpdates` and read `message.chat.id` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | optional Sheets sync | Google Cloud Console → service account → JSON key; share your sheet with the service account's email |
| `PIPELINE_SHEET_ID` | optional Sheets sync | the id in your Google Sheet's URL |

With no keys at all: the collector still runs, still filters and stores
jobs, just skips scoring (`score: null`) and skips Telegram. Nothing crashes.

### 2. Enable the workflow

The cron in `collect.yml` starts firing as soon as it's on the default
branch — nothing else to flip on. To run it once immediately: **Actions →
Collect job matches → Run workflow**.

### 3. Enable GitHub Pages

**Settings → Pages → Source: Deploy from a branch → Branch: `main` /
`(root)`**. The dashboard lives at `https://<you>.github.io/<repo>/docs/` —
note it's under `/docs/`, because `docs/index.html` fetches `../data/*.json`
as a relative path, which only resolves correctly when Pages serves the
whole repo (not just the `docs/` folder as its own root).

### 4. Add your Google Alerts / RSS feeds (optional)

Paste feed URLs into `config.yaml` under `feeds:`. Google Alerts: create an
alert at [google.com/alerts](https://google.com/alerts), set delivery to
"RSS feed", then copy the feed URL it gives you.

## Editing `config.yaml`

This is the only file you should need to touch regularly.

**Add a company:**
```yaml
companies:
  - {slug: some-company, source: greenhouse}   # source: greenhouse | lever | ashby | workable | smartrecruiters
```
Find the slug from the company's public jobs page URL (see the table
above). Push it, wait for the next run (or trigger one manually), then
check System Health — if it shows 0 jobs and a failure, the slug or source
is wrong.

**Add a track:**
```yaml
tracks:
  - name: Some New Track
    include: [keyword one, keyword two]   # matched against job titles, case-insensitive
    resume_variant: some-resume.docx
    priority: low   # optional; shown as a badge on the dashboard, doesn't change alerting
```

**Adjust the experience cap:** `experience.max_years_required`. If the
dashboard's System Health (or `runs.json`'s `filter.dropped_experience`)
shows the experience filter dropping almost everything, the regex in
`src/filter.py::extract_min_years_required` may not be matching your
sources' phrasing — check a few raw `description` fields in `data/jobs.json`
for the run before this cap and see what pattern it's using.

**Adjust alert thresholds:** `alerts.min_score_high_priority` (instant push)
and `alerts.min_score_digest` (folded into the 08:00 IST daily digest).
Below the digest threshold, a match is dashboard-only.

## Tracking your pipeline

```
python scripts/track.py <job-id> saved
python scripts/track.py <job-id> applied --variant business-analyst.docx
python scripts/track.py <job-id> interview --notes "phone screen booked for Thu"
```
Status must be one of: `discovered, saved, applied, responded, interview,
offer, rejected`. Job ids come from `data/jobs.json` or the dashboard's Feed
view (run `python scripts/track.py` with no arguments to list known ids).

The **My funnel** dashboard tab reads `data/pipeline.json` directly — it's
the only view that tells you whether you're actually working the system.

### Optional: Google Sheets instead of the CLI

If `GOOGLE_SERVICE_ACCOUNT_JSON` and `PIPELINE_SHEET_ID` are set, the
workflow pulls sheet edits into `pipeline.json` at the start of every run
(see the "Optional — pull pipeline status" step in `collect.yml`). Sheet
layout: one row per job with columns `job_id, status, applied_at,
resume_variant, notes`. Push the current state to the sheet manually with
`python scripts/sheets_sync.py push`. This is entirely optional — the
system works fully without it.

## Debugging a dead source

1. Open the dashboard's **System Health** tab. A source that's failed 3 runs
   in a row is called out at the top.
2. Open `data/runs.json` and find the most recent run's `sources.<name>.failures`
   — each entry has the exact target (slug or feed URL) and error string.
3. Common causes:
   - **404 / "fetch failed"** — the slug is wrong, or the company moved off
     that ATS. Re-check their public jobs page URL.
   - **429 / "rate limited"** — the collector already backs off and skips
     that source for the run; it'll retry next run. If it's chronic, that
     source has fewer, larger batches than the shared 1 req/sec budget
     assumes — nothing to fix on your end.
   - **"unexpected response shape"** — the vendor changed their API. Compare
     a raw `curl <url>` response against the adapter's `_normalise()`
     function in `src/sources/<name>.py`.
4. If a source is genuinely dead (vendor discontinued the endpoint, or the
   company isn't on that ATS anymore), just remove it from `config.yaml`.

## How the pieces fit together

```
collect.py
  ├─ sources/*.py     fetch + normalise (never raises, returns [] on failure)
  ├─ filter.py         deterministic: seen → excluded title → track match →
  │                     location → experience band (in that order, cheapest first)
  ├─ score.py           LLM fit score on filter survivors only (5-30/run, often 0)
  ├─ notify.py          Telegram: instant push above high-priority threshold,
  │                     digest at 08:00 IST above digest threshold, silence otherwise
  └─ store.py           dedupe (seen.json) + append (jobs.json) + log (runs.json)
```

Every run appends one record to `data/runs.json` regardless of outcome —
including total failures, which are also capped to one Telegram alert per
day so a broken run doesn't spam you.

## Known limits (by design, not oversight)

- **Coverage is roughly half your target universe.** Startups, product
  companies, and global firms on modern ATS platforms (Greenhouse, Lever,
  Ashby, Workable, SmartRecruiters) are covered. Indian corporates on
  Darwinbox, Workday, or SuccessFactors are not — none of them expose a
  public API, and scraping them would break the zero-ToS-violation
  constraint this project is built around.
- **No Naukri, LinkedIn, Instahyre, or Indeed.** Same reason — no usable
  public API, and scraping breaks constantly and against ToS. Those stay
  manual.
- **No auto-applying.** This finds and scores roles; you still apply.
- **No applicant-count or conversion-rate stats anywhere.** The dashboard
  only charts what the data actually contains.
- **No resume tailoring.** `resume_variant` just names which file to use;
  producing it is a separate problem.

## Every dependency, pinned

See `requirements.txt`. The collector's core path (`sources/`, `filter.py`,
`score.py`, `notify.py`, `store.py`) only needs `PyYAML` — everything else
(HTTP, JSON, regex, XML) is Python stdlib on purpose, so there's less to
break while you're not looking at this for two weeks.
