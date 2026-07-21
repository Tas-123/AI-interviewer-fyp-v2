"""Save report JSON and optional HTML artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from core.config import settings
from reporting.renderers.html_renderer import render_report_html


def save_interview_report(report: dict) -> Path | None:
    """
    Persist report to disk.

    Aborted sessions go to reports/aborted/; all others to reports/.
    HTML is always written (including aborted) so demos never look report-less.
    Returns path written, or None if nothing saved.
    """
    report_type = (report.get("report_meta") or {}).get("report_type", "incomplete")
    filename = (report.get("report_meta") or {}).get("report_filename")

    if report_type == "aborted":
        target_dir = settings.aborted_reports_dir
    else:
        target_dir = settings.reports_dir

    target_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        session_id = (report.get("report_meta") or {}).get("session_id", "unknown")
        filename = f"interview_report_{session_id}.json"

    json_path = target_dir / filename
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    html_path = json_path.with_suffix(".html")
    html_path.write_text(render_report_html(report), encoding="utf-8")

    return json_path
