"""
Dialogue guard safety net for likely STT tail fragments.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.decision_engine import DecisionEngine
from dialogue.guards.domain_guard import DomainGuard
from dialogue.guards.incomplete_guard import IncompleteGuard
from dialogue.guards.types import GuardContext
from dialogue.transcript_quality import assess_transcript_quality
from dialogue.transcript_utils import clean_live_transcript


def _context_with_prior_answer():
    ctx = SimpleNamespace(
        transcript_history=[
            (
                "I used a vector database for embeddings and stored in my NLP project "
                "with FastAPI serving the model."
            )
        ],
        question_history=["How did you store and retrieve embeddings in your project?"],
    )

    def last_substantial_transcript(min_words=8):
        for text in reversed(ctx.transcript_history or []):
            words = str(text or "").strip().split()
            if len(words) >= min_words:
                return str(text).strip()
        return ""

    ctx.last_substantial_transcript = last_substantial_transcript
    return ctx


def test_tail_fragment_quality_flag():
    raw = "the model generalized well."
    cleaned = clean_live_transcript(raw)
    quality = assess_transcript_quality(raw, cleaned)
    assert quality.is_likely_tail_fragment is True
    assert "likely_tail_fragment" in quality.flags


def test_incomplete_guard_softens_tail_after_substantial_answer():
    guard = IncompleteGuard()
    raw = "database for that."
    cleaned = clean_live_transcript(raw)
    quality = assess_transcript_quality(raw, cleaned)
    ctx = GuardContext(
        transcript=cleaned,
        last_question="How did you store embeddings?",
        interview_context=_context_with_prior_answer(),
        transcript_quality=quality.to_dict(),
    )
    result = guard.check(ctx)
    assert result.triggered is True
    assert result.decision_type == "TAIL_FRAGMENT_CONTINUE"
    assert "only caught part" not in (result.response_text or "").lower()
    assert "database for that" not in (result.response_text or "")


def test_domain_guard_suppresses_off_topic_redirect_for_tail():
    guard = DomainGuard()
    raw = "deal with using the neighbor values."
    cleaned = clean_live_transcript(raw)
    quality = assess_transcript_quality(raw, cleaned)
    ctx = GuardContext(
        transcript=cleaned,
        last_question="How would you handle missing values in a dataset?",
        interview_context=SimpleNamespace(
            get_domain_redirect_count=lambda: 0,
            increment_domain_redirect=lambda: 1,
        ),
        transcript_quality=quality.to_dict(),
    )
    result = guard.check(ctx)
    assert result.triggered is True
    assert result.decision_type == "STAY_ON_QUESTION"
    assert result.metadata.get("tail_fragment") is True


def test_decision_engine_blocks_advance_on_tail_fragment():
    engine = DecisionEngine()
    context = SimpleNamespace(
        latest_answer_for_decision="the model generalized well.",
        latest_transcript_quality={
            "is_likely_tail_fragment": True,
            "is_noisy": False,
            "cleaned_word_count": 5,
        },
        question_history=["How did you evaluate your model?"],
        state=SimpleNamespace(value="technical"),
        turn_count=5,
        coverage=SimpleNamespace(
            current_domain="machine_learning",
            can_probe_domain=lambda _d: True,
            mark_domain_covered=lambda _d: None,
            mark_domain_probe=lambda _d: None,
            get_summary=lambda: {},
        ),
        current_domain="machine_learning",
    )

    adaptive_result = {
        "evaluation": {
            "overall_score": 4.0,
            "weighted_overall_score": 4.0,
            "weakest_dimension": "clarity",
        },
        "decision": {"type": "ADVANCE", "next_question": "Next topic?"},
    }

    result = engine.decide_from_adaptive(adaptive_result, context)
    assert result["decision_type"] == "STAY_ON_QUESTION"
    assert result.get("reason") == "tail_fragment_scoring_blocked"


if __name__ == "__main__":
    test_tail_fragment_quality_flag()
    test_incomplete_guard_softens_tail_after_substantial_answer()
    test_domain_guard_suppresses_off_topic_redirect_for_tail()
    test_decision_engine_blocks_advance_on_tail_fragment()
    print("[PASS] test_tail_fragment_guarding")
