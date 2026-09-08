"""Deterministic filtering. Runs before any LLM call — cheapest checks first.

Order (per the spec):
  1. Drop if already seen.
  2. Drop if title matches an excluded token.
  3. Keep only if title matches at least one track's include list.
  4. Location: keep if it matches open_to or looks remote.
  5. Experience band: drop if the *minimum* years stated exceeds the cap.

Returns (kept_jobs, stats) where stats is a dict of counts suitable for
runs.json, and every kept job gains `track`, `remote`, and
`experience_stated` fields.
"""
from __future__ import annotations

import re

# --- location normalisation -------------------------------------------------

# Maps a canonical open_to city name to substrings that should match it in
# messy, real-world location strings. Deliberately generous per the spec.
_CITY_ALIASES: dict[str, list[str]] = {
    "bengaluru": ["bengaluru", "bangalore", "blr", "ka-bangalore", "karnataka"],
    "mumbai": ["mumbai", "bombay", "maharashtra-mumbai", "navi mumbai"],
    "pune": ["pune"],
    "hyderabad": ["hyderabad", "secunderabad", "telangana"],
    "ahmedabad": ["ahmedabad", "amdavad"],
    "gandhinagar": ["gandhinagar", "gift city"],
    "delhi ncr": ["delhi", "new delhi", "gurugram", "gurgaon", "noida", "ncr", "faridabad"],
    "remote": ["remote", "work from home", "wfh", "anywhere", "distributed"],
}


def _canonical_city_key(name: str) -> str:
    return name.strip().lower()


def normalise_location(raw: str) -> str:
    """Lowercase, strip separators, collapse whitespace."""
    if not raw:
        return ""
    text = raw.lower()
    text = re.sub(r"[_/,|]+", " ", text)
    text = re.sub(r"\bin-ka-", " ", text)  # "IN-KA-Bangalore" style codes
    text = re.sub(r"\s+", " ", text).strip()
    return text


def location_matches_open_to(location: str, open_to: list[str], remote_flag: bool | None) -> bool:
    if remote_flag:
        return True
    norm = normalise_location(location)
    if not norm:
        # No location string at all — don't punish the job for a source
        # that omits it; let it through and let the LLM/human judge.
        return True
    for city in open_to:
        key = _canonical_city_key(city)
        aliases = _CITY_ALIASES.get(key, [key])
        if any(alias in norm for alias in aliases):
            return True
    return False


# --- title matching ----------------------------------------------------------


def title_has_excluded_token(title: str, exclude_titles: list[str]) -> str | None:
    norm = f" {title.lower()} "
    for token in exclude_titles:
        t = token.lower().strip()
        if not t:
            continue
        # word-ish boundary match so "manager" doesn't hit inside another word
        if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", norm):
            return token
    return None


def matching_track(title: str, tracks: list[dict]) -> dict | None:
    norm = title.lower()
    for track in tracks:
        for token in track.get("include", []):
            t = token.lower().strip()
            if not t:
                continue
            if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", norm):
                return track
    return None


# --- experience band ----------------------------------------------------------

_YEARS_UNIT = r"(?:years?|yrs?)"

_EXPERIENCE_PATTERNS = [
    # "3-5 years", "3 to 6 yrs", "3–5 years" (en-dash)
    re.compile(rf"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*\+?\s*{_YEARS_UNIT}\b", re.I),
    # "3+ years", "3+ yrs exp"
    re.compile(rf"(\d+(?:\.\d+)?)\s*\+\s*{_YEARS_UNIT}\b", re.I),
    # "minimum 4 years", "min. 4 yrs", "at least 4 years"
    re.compile(rf"(?:minimum|min\.?|at least)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*{_YEARS_UNIT}\b", re.I),
    # bare "4 years of experience" / "4 years experience"
    re.compile(rf"(\d+(?:\.\d+)?)\s*{_YEARS_UNIT}\s*(?:of\s*)?(?:relevant\s*|prior\s*)?experience\b", re.I),
]


def extract_min_years_required(text: str) -> float | None:
    """Best-effort extraction of the minimum years of experience stated.

    Returns None if no such figure is found anywhere in the text.
    """
    if not text:
        return None
    found: list[float] = []
    for pattern in _EXPERIENCE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                found.append(float(m.group(1)))
            except (ValueError, IndexError):
                continue
    if not found:
        return None
    return min(found)


# --- main entrypoint -----------------------------------------------------------


def filter_jobs(jobs: list[dict], config: dict, seen_ids: set[str]) -> tuple[list[dict], dict]:
    stats = {
        "input": len(jobs),
        "dropped_seen": 0,
        "dropped_excluded_title": 0,
        "dropped_no_track_match": 0,
        "dropped_location": 0,
        "dropped_experience": 0,
        "kept": 0,
    }

    profile = config.get("profile", {})
    open_to = profile.get("open_to", [])
    exclude_titles = config.get("exclude_titles", [])
    tracks = config.get("tracks", [])
    max_years = config.get("experience", {}).get("max_years_required", 3)

    kept: list[dict] = []

    for job in jobs:
        job_id = job.get("id")
        title = job.get("title") or ""

        if job_id in seen_ids:
            stats["dropped_seen"] += 1
            continue

        if title_has_excluded_token(title, exclude_titles):
            stats["dropped_excluded_title"] += 1
            continue

        track = matching_track(title, tracks)
        if track is None:
            stats["dropped_no_track_match"] += 1
            continue

        if not location_matches_open_to(job.get("location") or "", open_to, job.get("remote")):
            stats["dropped_location"] += 1
            continue

        min_years = extract_min_years_required(job.get("description") or "")
        if min_years is not None and min_years > max_years:
            stats["dropped_experience"] += 1
            continue

        job = dict(job)
        job["track"] = track.get("name")
        job["track_priority"] = track.get("priority", "normal")
        job["resume_variant"] = track.get("resume_variant")
        job["experience_stated"] = min_years is not None
        job["min_years_required"] = min_years
        kept.append(job)

    stats["kept"] = len(kept)
    return kept, stats
