"""
Read-only index over Report v2 JSON files on disk.

Source of truth: PROJECT_ROOT/reports/interview_report_*.json
Does not call the interview engine or scrape HTML.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# recruiter_dashboard/services -> recruiter_dashboard -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


def _safe_load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _card_from_report(report: dict[str, Any], path: Path) -> dict[str, Any]:
    meta = report.get("report_meta") or {}
    ratings = report.get("ratings_summary") or {}
    rec = ratings.get("final_recommendation") or {}
    overall = ratings.get("overall_performance") or {}
    html_path = path.with_suffix(".html")
    session_id = meta.get("session_id") or ""
    return {
        "session_id": session_id,
        "candidate_display_name": meta.get("candidate_display_name") or "Candidate",
        "role_title": meta.get("role_title") or "",
        "report_type": meta.get("report_type") or "incomplete",
        "generated_at": meta.get("generated_at") or "",
        "hire_signal": rec.get("signal") or "N/A",
        "overall_score": overall.get("score"),
        "overall_label": overall.get("label") or "",
        "json_file": path.name,
        "html_file": html_path.name if html_path.exists() else None,
        "has_html": html_path.exists(),
        "mtime": path.stat().st_mtime,
    }


def list_report_cards(*, include_aborted: bool = False) -> list[dict[str, Any]]:
    if not REPORTS_DIR.is_dir():
        return []

    cards: list[dict[str, Any]] = []
    patterns = [REPORTS_DIR.glob("interview_report_*.json")]
    if include_aborted:
        aborted = REPORTS_DIR / "aborted"
        if aborted.is_dir():
            patterns.append(aborted.glob("interview_report_*.json"))

    for group in patterns:
        for path in group:
            report = _safe_load(path)
            if not report:
                continue
            cards.append(_card_from_report(report, path))

    cards.sort(
        key=lambda c: (c.get("generated_at") or "", c.get("mtime") or 0),
        reverse=True,
    )
    # Drop internal mtime from API response
    for c in cards:
        c.pop("mtime", None)
    return cards


def _find_json_path(session_id: str) -> Path | None:
    session_id = (session_id or "").strip()
    if not session_id or not REPORTS_DIR.is_dir():
        return None

    short = session_id[:8]
    # Fast path: filename contains short session id
    for path in REPORTS_DIR.glob(f"interview_report_*_{short}.json"):
        report = _safe_load(path)
        if report and (report.get("report_meta") or {}).get("session_id") == session_id:
            return path

    aborted = REPORTS_DIR / "aborted"
    if aborted.is_dir():
        for path in aborted.glob(f"interview_report_*_{short}.json"):
            report = _safe_load(path)
            if report and (report.get("report_meta") or {}).get("session_id") == session_id:
                return path

    # Slow path: scan all
    for path in REPORTS_DIR.glob("interview_report_*.json"):
        report = _safe_load(path)
        if report and (report.get("report_meta") or {}).get("session_id") == session_id:
            return path
    if aborted.is_dir():
        for path in aborted.glob("interview_report_*.json"):
            report = _safe_load(path)
            if report and (report.get("report_meta") or {}).get("session_id") == session_id:
                return path
    return None


def get_report(session_id: str) -> dict[str, Any] | None:
    path = _find_json_path(session_id)
    if not path:
        return None
    report = _safe_load(path)
    if not report:
        return None
    html_path = path.with_suffix(".html")
    return {
        "session_id": session_id,
        "json_file": path.name,
        "html_file": html_path.name if html_path.exists() else None,
        "html_path": str(html_path) if html_path.exists() else None,
        "json_path": str(path),
        "report": report,
    }


def get_html_path(session_id: str) -> Path | None:
    path = _find_json_path(session_id)
    if not path:
        return None
    html_path = path.with_suffix(".html")
    return html_path if html_path.exists() else None
