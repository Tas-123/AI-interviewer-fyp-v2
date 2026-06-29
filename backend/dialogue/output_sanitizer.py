"""Post-generation sanitization for interviewer-only spoken output."""

from __future__ import annotations

import re

from core.interviewer_policy import COACHING_PHRASE_BLOCKLIST


def sanitize_interviewer_output(text: str) -> str:
    """
    Strip coaching tone and enforce single-question spoken output.
    """
    if not text:
        return text

    cleaned = text.strip()
    lower = cleaned.lower()

    for phrase in COACHING_PHRASE_BLOCKLIST:
        if phrase in lower:
            idx = lower.find(phrase)
            cleaned = cleaned[:idx].strip()
            lower = cleaned.lower()
            break

    if cleaned.count("?") > 1:
        first_q = cleaned.find("?")
        cleaned = cleaned[: first_q + 1].strip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or text.strip()
