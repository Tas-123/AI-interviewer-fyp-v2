"""
Phase 6C — Score profiles, not_assessed domains, completion reporting.
"""

from __future__ import annotations

from dialogue.analytics import (
    build_domain_assessment_map,
    build_interview_completion_summary,
    generate_final_report,
)
from dialogue.context import InterviewContext
from dialogue.states import InterviewState
from evaluation.rubric import aggregate_profile_scores


def _sample_context() -> InterviewContext:
    ctx = InterviewContext({
        "name": "Test",
        "skills": ["python", "machine learning", "model evaluation"],
        "target_role": "junior_ai_engineer",
    })
    ctx.state = InterviewState.WRAPUP
    ctx.mark_domain_assessed("python")
    ctx.mark_domain_skipped("machine_learning")
    ctx.add_turn("How do you structure a Python ML project?", "I use modules and tests.")
    ctx.add_evaluation({
        "clarity": 3.0,
        "structure": 3.5,
        "confidence": 3.0,
        "ownership": 4.0,
        "leadership": 3.0,
        "result_orientation": 3.5,
        "overall_score": 3.4,
        "weighted_overall_score": 3.45,
        "hire_signal": "Hire",
    })
    ctx.add_adaptive_trace({
        "turn": 1,
        "question_answered": "How do you structure a Python ML project?",
        "candidate_answer": "I use modules and tests.",
        "domain": "python",
        "guard_passed": True,
        "scores": {"weighted_overall_score": 3.45},
    })
    return ctx


def test_aggregate_profile_scores_separates_communication_and_technical():
    scored = [{
        "clarity": 4.0,
        "structure": 3.0,
        "confidence": 3.0,
        "ownership": 2.0,
        "leadership": 2.5,
        "result_orientation": 3.0,
        "overall_score": 3.0,
    }]
    profiles = aggregate_profile_scores(scored)
    assert profiles["communication"]["composite"] == 3.33
    assert profiles["technical"]["composite"] == 2.5
    assert profiles["turns_included"] == 1


def test_domain_assessment_map_marks_not_assessed():
    ctx = _sample_context()
    skill_map = {
        "python": {"status": "covered_strong", "coverage_reason": "scored"},
        "machine learning": {"status": "not_assessed", "coverage_reason": "skipped"},
    }
    assessment = build_domain_assessment_map(ctx, skill_map)
    assert assessment["python"]["status"].startswith("covered")
    assert assessment["machine_learning"]["status"] == "not_assessed"


def test_generate_final_report_includes_phase6c_sections():
    report = generate_final_report(_sample_context())
    assert "score_profile_summary" in report
    assert report["score_profile_summary"]["turns_included"] >= 1
    assert "domain_assessment_map" in report
    assert "interview_completion" in report
    assert report["interview_completion"]["blueprint_domains_total"] >= 1
    assert "not_assessed_domains" in report["interview_completion"]


def test_interview_completion_summary_counts_assessed():
    ctx = _sample_context()
    skill_map = {"python": {"status": "covered_strong"}}
    assessment = build_domain_assessment_map(ctx, skill_map)
    completion = build_interview_completion_summary(ctx, assessment)
    assert completion["completed"] is True
    assert completion["domains_assessed"] >= 1


if __name__ == "__main__":
    test_aggregate_profile_scores_separates_communication_and_technical()
    test_domain_assessment_map_marks_not_assessed()
    test_generate_final_report_includes_phase6c_sections()
    test_interview_completion_summary_counts_assessed()
    print("[PASS] test_phase6c_reporting")
