"""
FYP-stage memory upgrades — recent Q&A injection + sliding question history.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.context import InterviewContext
from dialogue.llm_adapter import LLMAdapter


def _make_context() -> InterviewContext:
    return InterviewContext(
        {
            "name": "Candidate",
            "role": "Junior AI Engineer",
            "skills": ["python", "fastapi"],
            "experience": "2 years",
            "target_role": "junior_ai_engineer",
            "profile_source": "default",
        }
    )


def test_get_recent_qa_pairs_aligns_answer_to_prior_question():
    ctx = _make_context()
    ctx.add_turn("Please introduce yourself.", "")
    ctx.add_turn(
        "How would you structure a Python ML project?",
        "I used FastAPI and Docker in my internship.",
    )
    ctx.add_turn(
        "How do you detect overfitting?",
        "I use a validation set and regularization.",
    )

    pairs = ctx.get_recent_qa_pairs(n=3)
    assert len(pairs) == 2
    assert "introduce yourself" in pairs[0][0].lower()
    assert "fastapi" in pairs[0][1].lower()
    assert "python ml" in pairs[1][0].lower()
    assert "overfitting" not in pairs[1][0].lower()
    assert "validation" in pairs[1][1].lower()


def test_get_recent_qa_pairs_includes_pending_answer():
    ctx = _make_context()
    ctx.add_turn("Please introduce yourself.", "")
    ctx.add_turn(
        "How do you deploy models?",
        "I containerize with Docker.",
    )
    ctx.latest_answer_for_decision = (
        "I monitor latency with Prometheus after deploy."
    )

    pairs = ctx.get_recent_qa_pairs(n=3)
    assert pairs
    assert pairs[-1][0] == "How do you deploy models?"
    assert "prometheus" in pairs[-1][1].lower()


def test_format_recent_qa_for_prompt_soft_char_cap():
    ctx = _make_context()
    ctx.add_turn("Q1?", "")
    ctx.add_turn("Q2 next?", "A" * 500)
    text = ctx.format_recent_qa_for_prompt(n=3, max_chars=80)
    assert text.startswith("Relevant interview memory")
    assert len(text) <= 80
    assert text.endswith("...")


def test_build_history_text_uses_sliding_window():
    adapter = LLMAdapter.__new__(LLMAdapter)
    ctx = SimpleNamespace(
        question_history=[f"Question number {i}?" for i in range(1, 10)]
    )
    text = adapter._build_history_text(ctx)
    assert "Question number 4?" in text
    assert "Question number 9?" in text
    assert "Question number 1?" not in text
    assert text.startswith("4.")


def test_generate_followup_includes_recent_answer():
    adapter = LLMAdapter.__new__(LLMAdapter)
    adapter.model = "test-model"
    adapter.client = MagicMock()

    ctx = _make_context()
    ctx.add_turn("How do you expose a model via API?", "")
    ctx.latest_answer_for_decision = "I use FastAPI with pydantic schemas."

    captured = {}

    def fake_call(prompt):
        captured["prompt"] = prompt
        return "What status codes would you return for validation errors?"

    with patch.object(adapter, "_call_llm", side_effect=fake_call):
        out = adapter._generate_followup(
            {"topic": "apis_backend", "domain": "apis_backend", "difficulty": "easy"},
            ctx,
        )

    assert "fastapi" in captured["prompt"].lower()
    assert "Relevant interview memory" in captured["prompt"]
    assert "validation errors" in out.lower()


if __name__ == "__main__":
    test_get_recent_qa_pairs_aligns_answer_to_prior_question()
    test_get_recent_qa_pairs_includes_pending_answer()
    test_format_recent_qa_for_prompt_soft_char_cap()
    test_build_history_text_uses_sliding_window()
    test_generate_followup_includes_recent_answer()
    print("[PASS] test_recent_qa_memory")
