"""Small text helpers shared by every source adapter."""
from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")

DESCRIPTION_MAX_CHARS = 4000


def html_to_text(raw: str | None) -> str:
    """Strip HTML tags down to readable plain text. Never raises."""
    if not raw:
        return ""
    try:
        text = re.sub(r"(?i)</(p|div|li|br|h[1-6])>", "\n", raw)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = _TAG_RE.sub("", text)
        text = html.unescape(text)
        text = _WS_RE.sub(" ", text)
        text = _BLANKLINES_RE.sub("\n\n", text)
        return text.strip()
    except Exception:
        return ""


def truncate(text: str, max_chars: int = DESCRIPTION_MAX_CHARS) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def looks_remote(*strings: str | None) -> bool | None:
    """Best-effort guess at whether a posting is remote from free text.

    Returns True/False when confident, None when the source gives no signal
    either way (filter.py treats None as "unknown, don't drop it").
    """
    haystack = " ".join(s for s in strings if s).lower()
    if not haystack:
        return None
    if "remote" in haystack:
        # "remote" but explicitly restricted to a country far from home base
        # is still "remote" for our purposes — keep it simple and generous.
        return True
    if "on-site" in haystack or "onsite" in haystack or "in office" in haystack:
        return False
    return None
