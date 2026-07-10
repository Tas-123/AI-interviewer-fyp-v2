"""Resolve human-readable report filenames."""

from __future__ import annotations

import re
from datetime import datetime, timezone


def slugify_candidate_name(name: str | None) -> str:
    if not name or not str(name).strip():
        return "unknown_candidate"
    slug = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())
    slug = slug.strip("_")
    return slug or "unknown_candidate"


def build_report_filename(
    *,
    candidate_name: str | None,
    session_id: str | None,
    generated_at: datetime | None = None,
) -> str:
    """interview_report_{slug}_{YYYYMMDD_HHMM}_{short_id}.json"""
    when = generated_at or datetime.now(timezone.utc)
    timestamp = when.strftime("%Y%m%d_%H%M")
    slug = slugify_candidate_name(candidate_name)
    short_id = (session_id or "nosession")[:8]
    return f"interview_report_{slug}_{timestamp}_{short_id}.json"
