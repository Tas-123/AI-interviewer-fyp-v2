"""Voice UX demo fixes — domain-strict asks, hint path, short questions, STT fairness, Groq logs."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dialogue.context import InterviewContext
from dialogue.guards.idk_guard import IdkGuard
from dialogue.guards.types import GuardContext
from dialogue.groq_debug_log import log_groq_exchange
from dialogue.idk_policy import is_hint_request
from dialogue.llm_adapter import LLMAdapter, DOMAIN_QUESTION_SEEDS
from dialogue.question_selector import QuestionSelector
from evaluation.rubric import (
    apply_transcript_quality_adjustment,
    compute_weighted_score,
    should_apply_transcript_quality_adjustment,
)


PRODUCTIVITY_TOOL_Q = (
    "Tell me about a time you introduced a new tool or process that improved "
    "team productivity."
)


def test_python_domain_never_returns_role_specific_bank():
    selector = QuestionSelector()
    q = selector.select_for_domain("python")
    assert q is None, f"expected None for python (seed path), got: {q!r}"
    assert q != PRODUCTIVITY_TOOL_Q

    # Even with an empty asked list and bank loaded, technical domains stay closed.
    for domain in (
        "python",
        "machine_learning",
        "data_preprocessing",
        "model_evaluation",
        "nlp_speech_ai",
        "apis_backend",
        "deployment",
        "debugging_problem_solving",
    ):
        got = QuestionSelector().select_for_domain(domain)
        assert got is None, f"{domain} must not fall back to bank, got: {got!r}"
        if got:
            assert "productivity" not in got.lower()


def test_hint_request_routes_to_hint_idk():
    assert is_hint_request("give me a hint, I don't get it")
    assert is_hint_request("any hint please")
    assert is_hint_request("help me with this")

    ctx = InterviewContext(
        {
            "skills": ["Python"],
            "experience": "1 year",
            "role": "Junior AI Engineer",
            "target_role": "junior_ai_engineer",
        }
    )
    core = "How would you structure a small ML project in Python?"
    ctx.set_active_question(core)
    ctx.current_domain = "python"

    hit = IdkGuard().check(
        GuardContext(
            transcript="give me a hint… I don't get it",
            last_question=core,
            interview_context=ctx,
        )
    )
    assert hit.triggered
    assert hit.metadata.get("hint_request") is True
    assert hit.metadata.get("flow_action") == "hint_idk"
    assert "here's a small hint" in hit.response_text.lower()


def test_voice_question_limits_reject_long_and_multi_ask():
    long_q = (
        "Can you walk me through how you would structure a Python ML project, "
        "including modules, tests, logging, packaging, and also how you would "
        "debug failures in production after deployment?"
    )
    assert LLMAdapter._enforce_voice_question_limits(long_q) is None
    assert LLMAdapter._enforce_voice_question_limits(
        "Short ask one? And another ask two?"
    ) is None
    ok = "In Python, how would you keep a small ML project easy to debug?"
    assert LLMAdapter._enforce_voice_question_limits(ok) == ok

    clipped = LLMAdapter._clip_spoken_question(
        "First question here? Second question here too?"
    )
    assert clipped.count("?") == 1
    assert "Second" not in clipped


def test_stutter_flags_trigger_transcript_fairness():
    assert should_apply_transcript_quality_adjustment(
        {"is_noisy": False, "flags": ["stutter_prefix"], "reduction_ratio": 0.05}
    )
    assert should_apply_transcript_quality_adjustment(
        {"is_noisy": False, "flags": [], "reduction_ratio": 0.25}
    )
    assert not should_apply_transcript_quality_adjustment(
        {"is_noisy": False, "flags": [], "reduction_ratio": 0.05}
    )

    evaluation = {
        "clarity": 1.0,
        "structure": 1.5,
        "confidence": 2.0,
        "ownership": 4.0,
        "leadership": 3.5,
        "result_orientation": 4.0,
        "overall_score": 3.0,
        "weighted_overall_score": compute_weighted_score(
            {
                "clarity": 1.0,
                "structure": 1.5,
                "confidence": 2.0,
                "ownership": 4.0,
                "leadership": 3.5,
                "result_orientation": 4.0,
            }
        ),
        "hire_signal": "Borderline",
    }
    baseline = evaluation["weighted_overall_score"]
    adjusted = apply_transcript_quality_adjustment(
        evaluation,
        {
            "is_noisy": False,
            "flags": ["stutter_prefix"],
            "reduction_ratio": 0.12,
            "stutter_prefix": True,
        },
    )
    assert adjusted["transcript_quality_adjusted"] is True
    assert adjusted["weighted_overall_score"] >= baseline


def test_groq_debug_log_writes_when_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "live_interview_debug.log"

        class _Settings:
            debug_live_logging = True
            live_debug_log = log_path

        with patch("core.config.settings", _Settings()):
            log_groq_exchange("GROQ_QUESTION_PROMPT", "Ask about Python structure.")
            log_groq_exchange("GROQ_QUESTION_REPLY", "How would you structure it?")

        text = log_path.read_text(encoding="utf-8")
        assert "GROQ_QUESTION_PROMPT" in text
        assert "GROQ_QUESTION_REPLY" in text
        assert "Ask about Python structure" in text


def test_python_seed_exists_for_fallback():
    assert "python" in DOMAIN_QUESTION_SEEDS
    assert "python" in DOMAIN_QUESTION_SEEDS["python"].lower() or "structure" in (
        DOMAIN_QUESTION_SEEDS["python"].lower()
    )


if __name__ == "__main__":
    tests = [
        test_python_domain_never_returns_role_specific_bank,
        test_hint_request_routes_to_hint_idk,
        test_voice_question_limits_reject_long_and_multi_ask,
        test_stutter_flags_trigger_transcript_fairness,
        test_groq_debug_log_writes_when_enabled,
        test_python_seed_exists_for_fallback,
    ]
    for fn in tests:
        fn()
        print(f"[PASS] {fn.__name__}")
    print(f"[PASS] {len(tests)}/{len(tests)} voice UX demo fixes")
