"""Coverage-first wrap-up and full Junior AI Engineer blueprint policy tests."""

from __future__ import annotations

from dialogue.context import InterviewContext
from dialogue.decision_engine import DecisionEngine
from dialogue.guards.incomplete_guard import IncompleteGuard
from dialogue.guards.intent_guard import classify_candidate_intent
from dialogue.guards.meta_conversation_guard import MetaConversationGuard, classify_meta_intent
from dialogue.guards.types import GuardContext
from dialogue.states import InterviewState
from dialogue.transcript_utils import merge_stt_hypothesis
from reporting.completion_policy import classify_report_type


def _ctx() -> InterviewContext:
    return InterviewContext({
        "name": "Test",
        "skills": ["python"],
        "target_role": "junior_ai_engineer",
    })


def test_max_turns_raised_to_28():
    ctx = _ctx()
    assert ctx.max_total_interview_turns == 28


def test_decide_from_adaptive_does_not_close_at_turn_12_with_open_domains():
    ctx = _ctx()
    ctx.state = InterviewState.TECHNICAL
    ctx.turn_count = 12
    ctx.set_current_domain("python")
    engine = DecisionEngine()

    result = engine.decide_from_adaptive(
        {
            "decision": {"type": "ADVANCE", "next_question": "Next?"},
            "evaluation": {"weighted_overall_score": 3.0, "overall_score": 3.0},
        },
        ctx,
    )
    assert result.get("decision_type") != "CLOSING"
    assert result.get("type") != "closing"
    assert result.get("domain")


def test_decide_closes_only_when_blueprint_exhausted():
    ctx = _ctx()
    ctx.state = InterviewState.TECHNICAL
    for domain in ctx.interview_blueprint:
        ctx.mark_domain_covered(domain)
    ctx.turn_count = 10
    ctx.set_current_domain("behavioral_ownership")
    engine = DecisionEngine()

    result = engine.decide_from_adaptive(
        {
            "decision": {"type": "ADVANCE", "next_question": ""},
            "evaluation": {"weighted_overall_score": 3.0, "overall_score": 3.0},
        },
        ctx,
    )
    assert result.get("type") == "closing" or result.get("decision_type") == "CLOSING"
    assert ctx.state == InterviewState.WRAPUP


def test_safety_ceiling_can_still_close():
    ctx = _ctx()
    ctx.state = InterviewState.TECHNICAL
    ctx.turn_count = 28
    engine = DecisionEngine()
    result = engine.decide_from_adaptive(
        {
            "decision": {"type": "ADVANCE", "next_question": ""},
            "evaluation": {"weighted_overall_score": 3.0, "overall_score": 3.0},
        },
        ctx,
    )
    assert result.get("type") == "closing" or result.get("decision_type") == "CLOSING"


def test_handle_technical_does_not_close_mid_blueprint_at_12():
    ctx = _ctx()
    ctx.state = InterviewState.TECHNICAL
    ctx.turn_count = 12
    engine = DecisionEngine()
    action = engine._handle_technical(ctx, "I used Python for preprocessing.")
    assert action.get("type") != "closing"
    assert action.get("domain")


def test_soft_next_question_not_skip():
    assert classify_candidate_intent("move to the next question") == "STAY_ON_QUESTION"
    assert classify_meta_intent("next question please") == "STAY_ON_QUESTION"


def test_previous_question_is_repeat_not_closing():
    assert classify_candidate_intent("ask the previous question") == "REPEAT_REQUEST"
    assert classify_meta_intent("go back to the previous question") == "PREVIOUS_QUESTION"


def test_hard_skip_still_works():
    assert classify_candidate_intent("skip this question") == "SKIP_REQUEST"
    assert classify_meta_intent("I don't have an answer") == "CHANGE_TOPIC"


def test_skip_budget_on_context():
    ctx = _ctx()
    assert ctx.can_skip_domain()
    ctx.record_skip()
    ctx.record_skip()
    assert not ctx.can_skip_domain()


def test_merge_drops_tiny_trailing_fragment():
    long = (
        "I built a classification model using random forest and handled missing "
        "values with median imputation then scaled numeric features"
    )
    merged = merge_stt_hypothesis(long, "Started.")
    assert "Started" not in merged
    assert "random forest" in merged.lower()


def test_incomplete_does_not_quote_micro_fragment():
    ctx = _ctx()
    ctx.transcript_history.append(
        "I trained a logistic regression model on the customer churn dataset "
        "and measured precision recall and f1 on a held out test set."
    )
    guard = IncompleteGuard()
    hit = guard.check(
        GuardContext(
            transcript="Started.",
            last_question="Tell me about a machine learning project you worked on.",
            interview_context=ctx,
        )
    )
    assert hit.triggered
    assert "Started" not in (hit.response_text or "")


def test_fifty_percent_wrap_is_partial_not_complete():
    ctx = _ctx()
    ctx.state = InterviewState.WRAPUP
    for domain in list(ctx.interview_blueprint)[:5]:
        ctx.mark_domain_assessed(domain)
        ctx.mark_domain_covered(domain)
        ctx.add_evaluation({
            "overall_score": 3.0,
            "weighted_overall_score": 3.0,
        })
    # Visited coverage ~50%
    assert classify_report_type(ctx, 50.0) == "partial"
    assert classify_report_type(ctx, 100.0) == "complete"


if __name__ == "__main__":
    tests = [
        test_max_turns_raised_to_28,
        test_decide_from_adaptive_does_not_close_at_turn_12_with_open_domains,
        test_decide_closes_only_when_blueprint_exhausted,
        test_safety_ceiling_can_still_close,
        test_handle_technical_does_not_close_mid_blueprint_at_12,
        test_soft_next_question_not_skip,
        test_previous_question_is_repeat_not_closing,
        test_hard_skip_still_works,
        test_skip_budget_on_context,
        test_merge_drops_tiny_trailing_fragment,
        test_incomplete_does_not_quote_micro_fragment,
        test_fifty_percent_wrap_is_partial_not_complete,
    ]
    for fn in tests:
        fn()
        print(f"[PASS] {fn.__name__}")
