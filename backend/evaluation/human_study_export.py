"""
Human study export — offline CSV/JSON for manual rating and thesis κ analysis.

Phase 4: export scored turns for 15–20 human-rated answers validation study.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from evaluation.rubric import SCORE_DIMENSIONS


EXPORT_COLUMNS = [
    "turn",
    "domain",
    "question",
    "candidate_answer",
    *SCORE_DIMENSIONS,
    "overall_score",
    "weighted_overall_score",
    "weakest_dimension",
    "hire_signal",
    "rethink_applied",
    "human_rating_overall",
    "human_rater_id",
    "human_notes",
]


def _trace_row(item: dict, turn_index: int) -> dict[str, Any]:
    scores = item.get("scores") or {}
    eval_method = item.get("evaluation_method") or {}
    return {
        "turn": item.get("turn", turn_index),
        "domain": item.get("domain", ""),
        "question": item.get("question_answered", ""),
        "candidate_answer": item.get("candidate_answer", ""),
        "clarity": scores.get("clarity", 0),
        "structure": scores.get("structure", 0),
        "confidence": scores.get("confidence", 0),
        "ownership": scores.get("ownership", 0),
        "leadership": scores.get("leadership", 0),
        "result_orientation": scores.get("result_orientation", 0),
        "overall_score": scores.get("overall_score", 0),
        "weighted_overall_score": scores.get("weighted_overall_score", 0),
        "weakest_dimension": item.get("weakest_dimension", ""),
        "hire_signal": item.get("hire_signal", ""),
        "rethink_applied": eval_method.get("rethink_applied", False),
        "human_rating_overall": "",
        "human_rater_id": "",
        "human_notes": "",
    }


def extract_rows_from_report(report: dict) -> list[dict[str, Any]]:
    """Extract rateable rows from a final report dict."""
    trace = report.get("adaptive_questioning_trace") or []
    rows = []
    for idx, item in enumerate(trace, start=1):
        if not item.get("guard_passed", True):
            continue
        if not item.get("candidate_answer"):
            continue
        rows.append(_trace_row(item, idx))
    return rows


def extract_rows_from_context(context) -> list[dict[str, Any]]:
    """Extract rows directly from InterviewContext adaptive trace."""
    rows = []
    for idx, item in enumerate(context.get_adaptive_trace(), start=1):
        if not item.get("guard_passed", True):
            continue
        if not item.get("candidate_answer"):
            continue
        rows.append(_trace_row(item, idx))
    return rows


def export_to_csv(rows: list[dict[str, Any]], output_path: str | Path) -> Path:
    """Write human-study CSV with empty human rating columns."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in EXPORT_COLUMNS})
    return path


def export_to_json(rows: list[dict[str, Any]], output_path: str | Path) -> Path:
    """Write human-study JSON bundle."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "human_study_v1",
        "instructions": (
            "Rate human_rating_overall 1-5 for each row. "
            "Leave human_rater_id and human_notes as needed for κ study."
        ),
        "columns": EXPORT_COLUMNS,
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_from_dialogue_manager(dm, output_dir: str | Path, basename: str = "human_study") -> dict[str, str]:
    """
    Export human-study files from a DialogueManager instance.

    Returns dict with csv and json paths.
    """
    rows = extract_rows_from_context(dm.context)
    out = Path(output_dir)
    csv_path = export_to_csv(rows, out / f"{basename}.csv")
    json_path = export_to_json(rows, out / f"{basename}.json")
    return {"csv": str(csv_path), "json": str(json_path), "row_count": len(rows)}


def export_from_report_file(report_path: str | Path, output_dir: str | Path, basename: str = "human_study") -> dict:
    """Export from a saved interview report JSON file."""
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if "report" in report:
        report = report["report"]
    rows = extract_rows_from_report(report)
    out = Path(output_dir)
    csv_path = export_to_csv(rows, out / f"{basename}.csv")
    json_path = export_to_json(rows, out / f"{basename}.json")
    return {"csv": str(csv_path), "json": str(json_path), "row_count": len(rows)}
