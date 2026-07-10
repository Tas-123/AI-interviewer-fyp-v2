"""Semantic domain guard — LLM relevance, redirect limits, follow-up bypass."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.context import InterviewContext
from dialogue.guards.domain_guard import DomainGuard, is_answer_relevant_to_question
from dialogue.guards.relevance import (
    RelevanceResult,
    is_follow_up_question,
    semantic_answer_relevance,
    should_redirect_for_relevance,
)
from dialogue.guards.types import GuardContext, GuardResult


def test_follow_up_bypasses_guard():
    q = "That's useful context, how did you handle feature engineering for weather?"
    assert is_follow_up_question(q)
    assert is_answer_relevant_to_question(
        "I pulled API weather data and built lag features.",
        q,
    )


def test_uncertain_llm_defaults_to_relevant():
    result = RelevanceResult(relevant=False, confidence=0.4, reason="test")
    assert not should_redirect_for_relevance(result)


def test_clear_irrelevant_redirects():
    result = RelevanceResult(relevant=False, confidence=0.9, reason="off_topic")
    assert should_redirect_for_relevance(result)


def test_redirect_cap_stops_loop():
    ctx_obj = InterviewContext({"skills": [], "target_role": "junior_ai_engineer"})
    ctx_obj.question_history.append(
        "How did you handle feature engineering for weather in your retail model?"
    )
    ctx_obj.guard_redirect_counts[ctx_obj._canonical_active_question()] = 2

    guard = DomainGuard()
    guard_ctx = GuardContext(
        transcript="Something unrelated about sports.",
        last_question=ctx_obj.question_history[-1],
        interview_context=ctx_obj,
        llm_client=MagicMock(),
        llm_model="test",
    )

    mock_result = RelevanceResult(relevant=False, confidence=0.95, reason="off")
    import dialogue.guards.domain_guard as dg

    original = dg.semantic_answer_relevance
    dg.semantic_answer_relevance = lambda *a, **k: mock_result
    try:
        result = guard.check(guard_ctx)
        assert not result.triggered
    finally:
        dg.semantic_answer_relevance = original


def test_mock_llm_relevant_answer_passes():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"relevant": true, "confidence": 0.92, "reason": "addresses weather features"}'
                )
            )
        ]
    )
    answer = (
        "I pulled historical weather data from an external API and aggregated "
        "it to daily sales intervals with lag features."
    )
    question = "How would you handle missing values before training?"
    assert is_answer_relevant_to_question(
        answer, question, llm_client=mock_client, llm_model="test"
    )


if __name__ == "__main__":
    test_follow_up_bypasses_guard()
    test_uncertain_llm_defaults_to_relevant()
    test_clear_irrelevant_redirects()
    test_redirect_cap_stops_loop()
    test_mock_llm_relevant_answer_passes()
    print("[PASS] test_semantic_domain_guard")
