"""LLM fit scoring. Only survivors of filter.py reach this — expect 5-30
jobs per run, often zero.

Provider: Google Gemini free tier (default model gemini-2.0-flash), with
Groq as a fallback if GEMINI_API_KEY is missing or every Gemini call fails.
Keys come from environment variables (GitHub secrets in Actions); never
commit a key.

Batches up to 10 jobs per call. If the API is unavailable or a batch fails
to parse, every job in it still comes through with score=None — a missing
score must never mean a missed job (see notify.py, which still forwards
unscored jobs to the digest).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from .http import USER_AGENT

BATCH_SIZE = 10
DESCRIPTION_CHARS_IN_PROMPT = 1500

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

PROFILE_BLOCK = """\
Candidate: Akshat Gupta. 1 year 2 months full-time experience.
Most recent: Deputy Manager, Commercial Banking Coverage, Axis Bank (Jun 2025 - Aug 2026).
Managed 200+ SME/corporate accounts, ~Rs 21 Cr portfolio across 4 branches, led 3 BDEs
and 2 BROs, 15% portfolio revenue growth. KYC/AML compliance monitoring, trade-finance
compliance, credit monitoring, MIS reporting. Worked with Product/Ops/Risk on Infiniti,
a digital current-account onboarding platform — gathered frontline friction feedback,
trained 4 branches, contributed to 15-20% TAT reduction.

Education: MBA Marketing & IT, TAPMI (2023-2025). B.Tech ECE, BVM (2019-2023, GPA 8.72,
rank 3/150).

Prior: NRSC/ISRO internship — sole software owner of a 4-person autonomous museum guide
robot (line-following, QR scanning, TTS, NLP query handling, BRD/FRD documentation).
Amul internship — retail audit, SKU/assortment analysis, distributor network analysis,
16% sales uplift.

Self-built: RAG banking assistant (LlamaIndex, Pinecone, LangChain, OpenAI, Twilio
WhatsApp). Email research automation (Make.com, OpenAI, Serper) across 100+ companies.
Portfolio segmentation model (K-Means). Banking churn analytics dashboard. Privacy
compliance assessment against DPDPA. ISO 27001 assessment with risk register.

Tools: SQL, Python (working level), Excel/LibreOffice advanced, Power BI (basic),
Make.com, Copilot. Certs: ISO 27001, NIST CSF, GRC Fundamentals, DPDPA, SOX 404,
ITGC Fundamentals, AWS AI & Cloud Fundamentals, Power BI, SQL, Python.

Targeting: Business Analyst, Data Analyst, AI Automation. Secondary: GRC/IT audit,
presales, product marketing. Not interested in field sales or retail branch RM roles.

Known gaps to weigh honestly: years of experience is the recurring screener risk.
No formal internal audit experience. No enterprise BI stack depth (no production
Power BI/DAX, no Tableau). No SaaS or product-company employment history.
"""

RUBRIC = """\
Scoring rubric (score 1-10, be honest, do not inflate):
- 9-10: inside the stated experience band, domain overlaps directly, no hard blocker.
- 7-8: reachable. One soft gap, band within a year of mine.
- 5-6: worth a look but a real gap exists.
- 1-4: hard blocker (years, mandatory credential, domain with no bridge).

A role demanding a credential I don't hold (CA, CFA, CS, CIPP) or 4+ years of
experience is a 3, not a 6. Do not let the candidate's self-built projects
substitute for professional experience the posting explicitly requires. The
`gap` field must be honest — never invent experience the candidate doesn't have.
"""

RESPONSE_INSTRUCTIONS = """\
Score each job below against the candidate profile and rubric. Return ONLY a
JSON array (no prose, no markdown fences), one object per job, each shaped
exactly as:
{"id": "<the job's id, copied verbatim>", "score": <integer 1-10>, "why": "<one line>", "gap": "<one line, honest>", "verdict": "apply|maybe|skip"}
"""


def _build_prompt(batch: list[dict]) -> str:
    job_blocks = []
    for job in batch:
        desc = (job.get("description") or "")[:DESCRIPTION_CHARS_IN_PROMPT]
        job_blocks.append(
            f"id: {job.get('id')}\n"
            f"title: {job.get('title')}\n"
            f"company: {job.get('company')}\n"
            f"location: {job.get('location')}\n"
            f"track: {job.get('track')}\n"
            f"description: {desc}"
        )
    jobs_text = "\n\n---\n\n".join(job_blocks)
    return f"{PROFILE_BLOCK}\n\n{RUBRIC}\n\n{RESPONSE_INSTRUCTIONS}\n\nJobs:\n\n{jobs_text}"


def _call_gemini(prompt: str, api_key: str) -> str:
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(prompt: str, api_key: str) -> str:
    # Groq's response_format=json_object mode requires the word "json" in the
    # prompt and doesn't support bare arrays on all models, so we skip it and
    # rely on RESPONSE_INSTRUCTIONS + lenient parsing instead.
    body = json.dumps(
        {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        GROQ_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    # Strip markdown fences if the model added them despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array found in model response")
    return json.loads(text[start : end + 1])


def _score_batch(batch: list[dict]) -> dict[str, dict]:
    """Returns {job_id: {score, why, gap, verdict}} for a single batch."""
    prompt = _build_prompt(batch)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")

    raw_text = None
    if gemini_key:
        try:
            raw_text = _call_gemini(prompt, gemini_key)
        except Exception as e:
            print(f"[score] Gemini call failed: {e}", file=sys.stderr)

    if raw_text is None and groq_key:
        try:
            raw_text = _call_groq(prompt, groq_key)
        except Exception as e:
            print(f"[score] Groq call failed: {e}", file=sys.stderr)

    if raw_text is None:
        if not gemini_key and not groq_key:
            print("[score] no GEMINI_API_KEY or GROQ_API_KEY set; skipping scoring", file=sys.stderr)
        return {}

    try:
        results = _extract_json_array(raw_text)
    except Exception as e:
        print(f"[score] failed to parse model response as JSON: {e}", file=sys.stderr)
        return {}

    out = {}
    for r in results:
        job_id = r.get("id")
        if not job_id:
            continue
        out[job_id] = {
            "score": r.get("score"),
            "why": r.get("why", ""),
            "gap": r.get("gap", ""),
            "verdict": r.get("verdict"),
        }
    return out


def score_jobs(jobs: list[dict]) -> list[dict]:
    """Adds score/why/gap/verdict to each job. Never drops a job — a job the
    scorer couldn't reach comes back with score=None instead of vanishing."""
    scored: list[dict] = []
    for i in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[i : i + BATCH_SIZE]
        results = _score_batch(batch)
        for job in batch:
            job = dict(job)
            result = results.get(job["id"])
            if result:
                job.update(result)
            else:
                job.setdefault("score", None)
                job.setdefault("why", "")
                job.setdefault("gap", "")
                job.setdefault("verdict", None)
            scored.append(job)
    return scored


if __name__ == "__main__":
    # Manual sanity check: python -m src.score < jobs.json (a JSON list)
    jobs = json.load(sys.stdin)
    print(json.dumps(score_jobs(jobs), indent=2))
