"""
Phase 6A — Interview flow tests (duplicate questions, meta, IDK, domain tracking).
"""

from __future__ import annotations

from dialogue.context import InterviewContext
from dialogue.coverage_engine import CoverageEngine
from dialogue.decision_engine import DecisionEngine
from dialogue.guards.idk_guard import IdkGuard
from dialogue.guards.meta_conversation_guard import (
    MetaConversationGuard,
    classify_meta_intent,
)
from dialogue.guards.types import GuardContext
from dialogue.idk_policy import is_idk_response
from dialogue.question_dedup import domain_primary_already_asked, is_semantic_duplicate
from core.role_registry import get_role_config


def _minimal_context() -> InterviewContext:
    return InterviewContext({"name": "Test", "skills": ["python"], "target_role": "junior_ai_engineer"})


def test_set_current_domain_survives_probe_sync():
    ctx = _minimal_context()
    ctx.set_current_domain("python")
    ctx.mark_domain_probe("python")
    assert ctx.current_domain == "python"
    assert ctx.coverage.current_domain == "python"


def test_domain_primary_already_asked():
    history = [
        "Let's talk about Python project structure. In a small ML project, how would you organize the code?"
    ]
    assert domain_primary_already_asked("python", history)
    assert not domain_primary_already_asked("machine_learning", history)


def test_is_semantic_duplicate():
    a = "Let's move to overfitting. How would you detect overfitting?"
    b = "How would you expose a trained model through a REST API?"
    assert is_semantic_duplicate(a, [a])
    assert not is_semantic_duplicate(a, [b])


def test_advance_skips_duplicate_primary_domain():
    ctx = _minimal_context()
    engine = DecisionEngine()
    python_q = (
        "Let's talk about Python project structure. In a small ML project, "
        "how would you organize the code so it stays clean, reusable, and easy to debug?"
    )
    ctx.question_history.append(python_q)
    ctx.mark_domain_covered("project_overview")
    ctx.set_current_domain("project_overview")

    next_domain = engine._advance_to_next_domain(ctx)
    assert next_domain == "machine_learning"


def test_meta_already_answered_intent():
    assert classify_meta_intent("I just answered you that already") == "ALREADY_ANSWERED"
    assert classify_meta_intent("can you change the question") == "CHANGE_TOPIC"
    assert classify_meta_intent("I use Python for preprocessing") is None


def test_meta_guard_skips_evaluation():
    guard = MetaConversationGuard()
    ctx = _minimal_context()
    hit = guard.check(
        GuardContext(
            transcript="Can you change the question?",
            last_question="How would you detect overfitting?",
            interview_context=ctx,
        )
    )
    assert hit.triggered
    assert hit.should_evaluate is False
    assert hit.metadata.get("flow_action") == "skip_domain"


def test_idk_detection():
    assert is_idk_response("Well, I don't know.")
    assert not is_idk_response(
        "I use regularization and L2 penalty on weights in my sklearn pipeline."
    )


def test_idk_guard_first_attempt_rephrase():
    guard = IdkGuard()
    interview = _minimal_context()
    interview.set_current_domain("python")
    hit = guard.check(
        GuardContext(
            transcript="I don't know",
            last_question="How would you structure a Python ML project?",
            interview_context=interview,
        )
    )
    assert hit.triggered
    assert hit.metadata.get("flow_action") == "rephrase_idk"
    assert hit.should_evaluate is False


def test_idk_third_attempt_skips_domain():
    guard = IdkGuard()
    interview = _minimal_context()
    interview.set_current_domain("python")
    interview.record_idk_attempt("python")
    interview.record_idk_attempt("python")
    hit = guard.check(
        GuardContext(
            transcript="I don't know",
            last_question="How would you structure a Python ML project?",
            interview_context=interview,
        )
    )
    assert hit.metadata.get("flow_action") == "skip_domain"


def test_coverage_engine_set_current_domain():
    cov = CoverageEngine(get_role_config())
    cov.set_current_domain("machine_learning")
    cov.mark_domain_probe("machine_learning")
    assert cov.current_domain == "machine_learning"


if __name__ == "__main__":
    tests = [
        test_set_current_domain_survives_probe_sync,
        test_domain_primary_already_asked,
        test_is_semantic_duplicate,
        test_advance_skips_duplicate_primary_domain,
        test_meta_already_answered_intent,
        test_meta_guard_skips_evaluation,
        test_idk_detection,
        test_idk_guard_first_attempt_rephrase,
        test_idk_third_attempt_skips_domain,
        test_coverage_engine_set_current_domain,
    ]
    for fn in tests:
        fn()
        print(f"[PASS] {fn.__name__}")
