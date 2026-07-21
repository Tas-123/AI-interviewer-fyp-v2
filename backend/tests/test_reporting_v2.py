"""
Report v2 module tests — completion policy, generator, persistence, HTML.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from dialogue.analytics import generate_final_report
from dialogue.context import InterviewContext
from dialogue.states import InterviewState
from reporting.completion_policy import classify_report_type, count_evaluated_turns
from reporting.generator import build_report_v2
from reporting.naming import build_report_filename, slugify_candidate_name
from reporting.narrative import generate_narrative_summaries
from reporting.persistence import save_interview_report
from reporting.renderers.html_renderer import render_report_html
from reporting.schema import PARTIAL_RECOMMENDATION_RATIONALE, REPORT_VERSION


def _evaluation(turn: int, score: float = 3.2) -> dict:
    return {
        "clarity": 3.0,
        "structure": 3.0,
        "confidence": 3.0,
        "ownership": 3.0,
        "leadership": 2.5,
        "result_orientation": 3.0,
        "overall_score": score,
        "weighted_overall_score": score,
        "hire_signal": "Borderline",
        "turn": turn,
    }


def _trace(turn: int, domain: str = "python") -> dict:
    return {
        "turn": turn,
        "question_answered": f"Question for turn {turn}?",
        "candidate_answer": f"Answer for turn {turn}.",
        "domain": domain,
        "guard_passed": True,
        "scores": {"weighted_overall_score": 3.2},
        "score_profiles": {
            "communication": {"composite": 3.0},
            "technical": {"composite": 3.1},
        },
        "hire_signal": "Borderline",
        "weakest_dimension": "structure",
        "follow_up_reason": "Answer sufficient; advancing to the next interview topic.",
        "decision_type": "ADVANCE",
    }


def _rich_context(
    *,
    wrapup: bool = True,
    evaluations: int = 5,
    cover_all_domains: bool = False,
) -> InterviewContext:
    ctx = InterviewContext({
        "name": "Alex Rivera",
        "skills": ["python", "machine learning"],
        "target_role": "junior_ai_engineer",
        "role": "Junior AI Engineer",
    })
    ctx.state = InterviewState.WRAPUP if wrapup else InterviewState.TECHNICAL
    domains = list(ctx.interview_blueprint)
    for i in range(1, evaluations + 1):
        domain = domains[(i - 1) % len(domains)]
        ctx.mark_domain_assessed(domain)
        ctx.mark_domain_covered(domain)
        ctx.add_turn(f"Q{i}", f"A{i}")
        ctx.add_evaluation(_evaluation(i))
        ctx.add_adaptive_trace(_trace(i, domain))
    if cover_all_domains:
        for domain in domains:
            ctx.mark_domain_assessed(domain)
            if ctx.domain_coverage.get(domain, 0) < 1:
                ctx.mark_domain_covered(domain)
    return ctx


def test_slugify_candidate_name():
    assert slugify_candidate_name("Alex Rivera") == "alex_rivera"
    assert slugify_candidate_name("") == "unknown_candidate"


def test_build_report_filename_includes_slug_and_timestamp():
    name = build_report_filename(
        candidate_name="Alex Rivera",
        session_id="af6be9a3-943d-4909-af13-26e605b55b92",
        generated_at=datetime(2026, 7, 10, 16, 50, tzinfo=timezone.utc),
    )
    assert name.startswith("interview_report_alex_rivera_20260710_1650_")
    assert name.endswith(".json")


def test_classify_report_type_tiers():
    ctx = _rich_context(wrapup=True, evaluations=10, cover_all_domains=True)
    legacy = generate_final_report(ctx)
    coverage = legacy["interview_completion"]["coverage_percent"]
    assert coverage >= 100.0
    assert classify_report_type(ctx, coverage) == "complete"

    # 50% wrap-up is partial under full-coverage policy
    partial_wrap = _rich_context(wrapup=True, evaluations=5)
    partial_wrap_legacy = generate_final_report(partial_wrap)
    partial_wrap_cov = partial_wrap_legacy["interview_completion"]["coverage_percent"]
    assert classify_report_type(partial_wrap, partial_wrap_cov) == "partial"

    partial_ctx = _rich_context(wrapup=False, evaluations=3)
    partial_legacy = generate_final_report(partial_ctx)
    partial_cov = partial_legacy["interview_completion"]["coverage_percent"]
    assert classify_report_type(partial_ctx, partial_cov) == "partial"

    empty_ctx = InterviewContext({"name": "X"})
    assert classify_report_type(empty_ctx, 0) == "aborted"


def test_build_report_v2_structure_and_backward_compat():
    ctx = _rich_context(wrapup=True, evaluations=10, cover_all_domains=True)
    legacy = generate_final_report(ctx)
    mock_llm = MagicMock()
    mock_llm.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "executive_summary": "Alex performed well in a full interview.",
                        "overall_summary": "A complete session with solid technical answers.",
                    })
                )
            )
        ]
    )

    report = build_report_v2(
        ctx,
        legacy,
        session_id="test-session-001",
        llm_client=mock_llm,
        llm_model="test-model",
    )

    assert report["report_version"] == REPORT_VERSION
    assert report["report_meta"]["report_type"] == "complete"
    assert report["executive_summary"]
    assert report["overall_summary"]
    assert report["ratings_summary"]["final_recommendation"]["signal"] != "N/A"
    assert report["question_review"]
    assert report["domain_ratings"]
    assert "detailed_analytics" in report
    assert report["weighted_score_summary"] == legacy["weighted_score_summary"]


def test_partial_report_forces_na_recommendation():
    ctx = _rich_context(wrapup=False, evaluations=3)
    legacy = generate_final_report(ctx)
    report = build_report_v2(ctx, legacy, session_id="partial-session")

    assert report["report_meta"]["report_type"] == "partial"
    rec = report["ratings_summary"]["final_recommendation"]
    assert rec["signal"] == "N/A"
    assert PARTIAL_RECOMMENDATION_RATIONALE in rec["rationale"]


def test_aborted_report_saved_to_aborted_directory():
    ctx = InterviewContext({"name": "No Data"})
    legacy = generate_final_report(ctx)
    report = build_report_v2(ctx, legacy, session_id="aborted-session-xyz")

    assert report["report_meta"]["report_type"] == "aborted"
    assert count_evaluated_turns(ctx) == 0

    with tempfile.TemporaryDirectory() as tmp:
        from core import config

        original_reports = config.settings.reports_dir
        original_aborted = config.settings.aborted_reports_dir
        object.__setattr__(config.settings, "reports_dir", Path(tmp) / "reports")
        object.__setattr__(config.settings, "aborted_reports_dir", Path(tmp) / "reports" / "aborted")

        path = save_interview_report(report)
        assert path is not None
        assert "aborted" in str(path)
        assert path.exists()
        html_path = path.with_suffix(".html")
        assert html_path.exists(), "Aborted reports must also write HTML for demo visibility"

        object.__setattr__(config.settings, "reports_dir", original_reports)
        object.__setattr__(config.settings, "aborted_reports_dir", original_aborted)


def test_html_renderer_includes_executive_summary():
    ctx = _rich_context(evaluations=3, wrapup=False)
    legacy = generate_final_report(ctx)
    report = build_report_v2(ctx, legacy, session_id="html-test")
    html = render_report_html(report)
    assert "Executive summary" in html
    assert "Recruiter interview assessment" in html
    assert "<h1>" in html
    name = report["report_meta"].get("candidate_display_name") or "Alex"
    assert name in html
    assert report["executive_summary"][:20] in html or name in html
    assert "Recommendation" in html
    assert "Domain assessment" in html


def test_narrative_fallback_without_llm():
    facts = {
        "report_type": "partial",
        "candidate_name": "Alex",
        "role_title": "Junior AI Engineer",
        "evaluated_turns": 3,
        "coverage_percent": 40,
        "overall_score": 2.8,
        "hire_signal": "N/A",
        "strengths": ["Structured answers"],
        "areas_for_improvement": ["More depth"],
    }
    executive, overall = generate_narrative_summaries(facts, llm_client=None)
    assert executive
    assert overall
    assert "preliminary" in executive.lower() or "Preliminary" in executive


if __name__ == "__main__":
    test_slugify_candidate_name()
    test_build_report_filename_includes_slug_and_timestamp()
    test_classify_report_type_tiers()
    test_build_report_v2_structure_and_backward_compat()
    test_partial_report_forces_na_recommendation()
    test_aborted_report_saved_to_aborted_directory()
    test_html_renderer_includes_executive_summary()
    test_narrative_fallback_without_llm()
    print("[PASS] test_reporting_v2")
