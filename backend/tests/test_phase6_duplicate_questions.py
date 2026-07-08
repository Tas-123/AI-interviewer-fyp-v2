"""Phase 6 — global duplicate question detection (PROBE path included)."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.dialogue_manager import DialogueManager
from dialogue.question_dedup import is_semantic_duplicate, similarity


def test_similarity_threshold_catches_near_paraphrase():
    a = "Tell me about an AI or machine learning project you worked on."
    b = "Tell me about an AI or machine learning project that you worked on recently."
    assert similarity(a, b) >= 0.80
    assert is_semantic_duplicate(b, [a])


def test_ensure_unique_replaces_duplicate_probe():
    dm = DialogueManager.__new__(DialogueManager)
    dm.engine = MagicMock()
    dm.engine._domain_to_topic = MagicMock(return_value="machine learning")
    dm.context = MagicMock()
    dm.context.question_history = [
        "How would you detect overfitting when training score is high but validation is low?"
    ]
    dm.context.current_domain = "machine_learning"

    duplicate = (
        "How would you detect overfitting when the training score is high "
        "but validation score is low?"
    )
    unique = DialogueManager._ensure_unique_question(dm, duplicate)
    assert unique != duplicate
    assert not is_semantic_duplicate(unique, dm.context.question_history)


def test_probe_path_applies_uniqueness():
    """Simulate adaptive PROBE branch: evaluator next_question must be deduped."""
    dm = DialogueManager.__new__(DialogueManager)
    dm.engine = MagicMock()
    dm.engine._domain_to_topic = MagicMock(return_value="python")
    dm.context = MagicMock()
    prior = "How do you organize Python project structure for clean reusable code?"
    dm.context.question_history = [prior]
    dm.context.current_domain = "python"

    probe_q = "How do you organize the Python project structure for clean, reusable, and easy to debug code?"
    out = DialogueManager._ensure_unique_question(dm, probe_q)
    assert out != probe_q
    assert "another angle" in out.lower() or "relevant experience" in out.lower()


if __name__ == "__main__":
    test_similarity_threshold_catches_near_paraphrase()
    test_ensure_unique_replaces_duplicate_probe()
    test_probe_path_applies_uniqueness()
    print("[PASS] test_phase6_duplicate_questions")
