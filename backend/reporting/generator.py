"""Orchestrate report v2 from InterviewContext and legacy analytics."""

from __future__ import annotations

from datetime import datetime, timezone

from reporting.builders import (
    build_domain_ratings,
    build_question_review,
    build_ratings_summary,
    build_strengths_and_improvements,
)
from reporting.completion_policy import (
    classify_report_type,
    completion_note_for_type,
    count_evaluated_turns,
    infer_termination_reason,
)
from reporting.naming import build_report_filename
from reporting.narrative import generate_narrative_summaries
from reporting.schema import LEGACY_TOP_LEVEL_KEYS, REPORT_VERSION


def build_report_v2(
    context,
    legacy_report: dict,
    *,
    session_id: str | None = None,
    termination_reason: str | None = None,
    interview_started_at: datetime | None = None,
    interview_ended_at: datetime | None = None,
    llm_client=None,
    llm_model: str | None = None,
) -> dict:
    """
    Wrap legacy analytics in report v2 structure.

    Mirrors legacy top-level keys for backward compatibility with existing UI/API.
    """
    legacy = dict(legacy_report or {})
    ended_at = interview_ended_at or datetime.now(timezone.utc)
    started_at = interview_started_at

    completion = legacy.get("interview_completion", {}) or {}
    coverage_percent = float(completion.get("coverage_percent", 0) or 0)
    evaluated_turns = count_evaluated_turns(context)

    report_type = classify_report_type(context, coverage_percent)
    termination = infer_termination_reason(context, termination_reason)

    candidate_name = (
        context.resume_data.get("name")
        or context.resume_data.get("display_name")
        or "Candidate"
    )
    role_title = legacy.get("interview_metadata", {}).get("role_title", "Junior AI Engineer")

    filename = build_report_filename(
        candidate_name=candidate_name,
        session_id=session_id,
        generated_at=ended_at,
    )

    domain_ratings = build_domain_ratings(legacy.get("domain_assessment_map", {}))
    question_review = build_question_review(legacy.get("adaptive_questioning_trace", []))
    ratings_summary = build_ratings_summary(legacy, report_type, evaluated_turns)
    strengths, areas_for_improvement = build_strengths_and_improvements(legacy)

    narrative_facts = {
        "report_type": report_type,
        "candidate_name": candidate_name,
        "role_title": role_title,
        "evaluated_turns": evaluated_turns,
        "coverage_percent": coverage_percent,
        "overall_score": ratings_summary["overall_performance"]["score"],
        "hire_signal": ratings_summary["final_recommendation"]["signal"],
        "strengths": strengths,
        "areas_for_improvement": areas_for_improvement,
        "domain_ratings": domain_ratings,
    }
    executive_summary, overall_summary = generate_narrative_summaries(
        narrative_facts,
        llm_client=llm_client,
        llm_model=llm_model,
    )

    extended_completion = {
        **completion,
        "report_type": report_type,
        "evaluated_turns": evaluated_turns,
        "termination_reason": termination,
        "completion_note": completion_note_for_type(report_type),
        "thresholds_met": {
            "complete": report_type == "complete",
            "partial": report_type == "partial",
        },
    }

    report_meta = {
        "report_version": REPORT_VERSION,
        "report_type": report_type,
        "session_id": session_id,
        "termination_reason": termination,
        "generated_at": ended_at.isoformat(),
        "interview_started_at": started_at.isoformat() if started_at else None,
        "interview_ended_at": ended_at.isoformat(),
        "candidate_display_name": candidate_name,
        "target_role": getattr(context, "target_role", "junior_ai_engineer"),
        "role_title": role_title,
        "report_filename": filename,
    }

    limitations = legacy.get("bias_awareness", {}) or {}
    if report_type != "complete":
        limitations = {
            **limitations,
            "data_quality_caveat": extended_completion["completion_note"],
        }

    v2 = {
        "report_version": REPORT_VERSION,
        "report_meta": report_meta,
        "executive_summary": executive_summary,
        "overall_summary": overall_summary,
        "ratings_summary": ratings_summary,
        "domain_ratings": domain_ratings,
        "strengths": strengths,
        "areas_for_improvement": areas_for_improvement,
        "question_review": question_review,
        "detailed_analytics": legacy,
        "limitations_and_bias": limitations,
        "interview_completion": extended_completion,
    }

    for key in LEGACY_TOP_LEVEL_KEYS:
        if key in legacy:
            v2[key] = legacy[key]

    # Keep interview_completion at root aligned with extended version.
    v2["interview_completion"] = extended_completion

    return v2
