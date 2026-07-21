"""Unit checks for demo pipeline stabilization fixes."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("GROQ_API_KEY", "mock-key")

from dialogue.context import InterviewContext
from dialogue.evaluator import Evaluator
from dialogue.guards.meta_conversation_guard import MetaConversationGuard
from dialogue.guards.types import GuardContext
from dialogue.llm_adapter import LLMAdapter
from dialogue.question_dedup import DOMAIN_PRIMARY_SIGNATURES, domain_primary_already_asked
from reporting.builders import build_question_review
from reporting.completion_policy import count_evaluated_turns
from reporting.persistence import save_interview_report


def test_question_review_includes_zero_score_and_idk():
    trace = [
        {
            "turn": 1,
            "question_answered": "Tell me about a project.",
            "candidate_answer": "I built a React portfolio site.",
            "domain": "project_overview",
            "guard_passed": True,
            "decision_type": "ADVANCE",
            "scores": {"weighted_overall_score": 2.5},
            "score_profiles": {
                "communication": {"composite": 2.5},
                "technical": {"composite": 2.0},
            },
            "hire_signal": "Borderline",
        },
        {
            "turn": 2,
            "question_answered": "How would you structure React components?",
            "candidate_answer": "I used modular files for the ML pipeline components.",
            "domain": "python",
            "guard_passed": True,
            "decision_type": "ADVANCE",
            "scores": {"weighted_overall_score": 0.0},
            "score_profiles": {},
            "hire_signal": "N/A",
            "is_error": True,
        },
        {
            "turn": 3,
            "question_answered": "In React, how would you lift state?",
            "candidate_answer": "I don't know.",
            "domain": "react_frontend",
            "guard_passed": False,
            "decision_type": "IDK_RESPONSE",
            "next_question": "That's okay — let me ask it more simply.",
            "scores": {},
        },
        {
            "turn": 4,
            "question_answered": "Off topic",
            "candidate_answer": "What's the weather?",
            "domain": "react_frontend",
            "guard_passed": False,
            "decision_type": "OFF_TOPIC",
            "scores": {},
        },
    ]
    reviews = build_question_review(trace)
    statuses = [r["review_status"] for r in reviews]
    assert "scored" in statuses
    assert "evaluation_unavailable" in statuses
    assert "redirect" in statuses
    assert len(reviews) == 3  # OFF_TOPIC excluded
    print("[PASS] test_question_review_includes_zero_score_and_idk")


def test_degraded_eval_counts_as_evaluated():
    ctx = InterviewContext({"name": "Sam", "target_role": "junior_frontend_developer"})
    ctx.add_evaluation(
        {
            "overall_score": 1.0,
            "weighted_overall_score": 1.0,
            "is_error": True,
            "evaluation_degraded": True,
        }
    )
    assert count_evaluated_turns(ctx) == 1
    print("[PASS] test_degraded_eval_counts_as_evaluated")


def test_fallback_adaptive_floors_substantial_answers():
    ev = Evaluator(role_title="Junior Frontend Developer")
    result = ev._fallback_adaptive_result(
        answer="I would use fetch with async await and show a loading spinner while waiting."
    )
    evaluation = result["evaluation"]
    assert evaluation["overall_score"] >= 1.0
    assert evaluation.get("evaluation_degraded") is True
    print("[PASS] test_fallback_adaptive_floors_substantial_answers")


def test_soft_advance_escalates_on_second_ask():
    ctx = InterviewContext({"name": "Sam", "target_role": "junior_frontend_developer"})
    ctx.set_current_domain("react_frontend")
    guard = MetaConversationGuard()

    first = guard.check(
        GuardContext(
            transcript="next question please",
            last_question="In React, how would you lift state?",
            interview_context=ctx,
        )
    )
    assert first.triggered
    assert first.decision_type == "STAY_ON_QUESTION"
    assert first.metadata.get("flow_action") == "stay_on_question"

    second = guard.check(
        GuardContext(
            transcript="next question",
            last_question="In React, how would you lift state?",
            interview_context=ctx,
        )
    )
    assert second.triggered
    assert second.metadata.get("flow_action") == "skip_domain"
    assert second.metadata.get("force_advance") is True
    print("[PASS] test_soft_advance_escalates_on_second_ask")


def test_idk_plus_next_question_defers_to_idk_guard():
    ctx = InterviewContext({"name": "Sam", "target_role": "junior_frontend_developer"})
    ctx.set_current_domain("react_frontend")
    guard = MetaConversationGuard()
    result = guard.check(
        GuardContext(
            transcript="I don't know, next question",
            last_question="In React, how would you lift state?",
            interview_context=ctx,
        )
    )
    assert result.triggered is False
    print("[PASS] test_idk_plus_next_question_defers_to_idk_guard")


def test_frontend_primary_signatures_exist():
    for domain in ("html_css", "javascript", "react_frontend", "frontend_apis"):
        assert domain in DOMAIN_PRIMARY_SIGNATURES
    assert domain_primary_already_asked(
        "react_frontend",
        ["In React, how would you structure components and state for a small feature?"],
    )
    print("[PASS] test_frontend_primary_signatures_exist")


def test_question_gen_error_uses_seed_fallback():
    adapter = LLMAdapter.__new__(LLMAdapter)
    ctx = InterviewContext({"name": "Sam", "target_role": "junior_frontend_developer"})
    ctx.set_current_domain("react_frontend")
    out = adapter._ensure_spoken_question(
        "[Error generating question. Please try again.]",
        ctx,
        domain="react_frontend",
    )
    assert "Error generating" not in out
    assert "React" in out or "react" in out.lower() or "component" in out.lower()
    print("[PASS] test_question_gen_error_uses_seed_fallback")


def test_aborted_report_writes_html():
    from dialogue.analytics import generate_final_report
    from reporting.generator import build_report_v2
    from core import config

    ctx = InterviewContext({"name": "No Data", "target_role": "junior_frontend_developer"})
    legacy = generate_final_report(ctx)
    report = build_report_v2(ctx, legacy, session_id="aborted-demo-html")
    assert report["report_meta"]["report_type"] == "aborted"

    with tempfile.TemporaryDirectory() as tmp:
        original_reports = config.settings.reports_dir
        original_aborted = config.settings.aborted_reports_dir
        object.__setattr__(config.settings, "reports_dir", Path(tmp) / "reports")
        object.__setattr__(
            config.settings, "aborted_reports_dir", Path(tmp) / "reports" / "aborted"
        )
        try:
            path = save_interview_report(report)
            assert path is not None
            assert path.with_suffix(".html").exists()
        finally:
            object.__setattr__(config.settings, "reports_dir", original_reports)
            object.__setattr__(config.settings, "aborted_reports_dir", original_aborted)
    print("[PASS] test_aborted_report_writes_html")


if __name__ == "__main__":
    tests = [
        test_question_review_includes_zero_score_and_idk,
        test_degraded_eval_counts_as_evaluated,
        test_fallback_adaptive_floors_substantial_answers,
        test_soft_advance_escalates_on_second_ask,
        test_idk_plus_next_question_defers_to_idk_guard,
        test_frontend_primary_signatures_exist,
        test_question_gen_error_uses_seed_fallback,
        test_aborted_report_writes_html,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1
    sys.exit(1 if failed else 0)
