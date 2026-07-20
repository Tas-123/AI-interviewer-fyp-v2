"""Phase 6 — natural conversation phrasing (openers + softer redirects)."""

from __future__ import annotations

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.guards.domain_guard import domain_relevance_redirect_response
from dialogue.guards.intent_guard import intent_redirect_response
from dialogue.llm_adapter import _naturalize_static_question


def test_naturalize_seed0_has_no_lets_talk_frame():
    q = _naturalize_static_question(
        "python",
        "In Python, how would you structure a small machine learning project?",
        variety_seed=0,
    )
    assert "let's talk" not in q.lower()
    assert "organize the code" in q.lower()


def test_naturalize_rotates_openers():
    # Seeds 0–2 are empty openers; seed 3 adds "Alright —".
    bare = _naturalize_static_question("python", "x", variety_seed=0)
    with_opener = _naturalize_static_question("python", "x", variety_seed=3)
    assert "organize the code" in bare.lower()
    assert with_opener.startswith("Alright")
    assert "organize the code" in with_opener.lower()
    # Resume/bank path keeps question text (no domain-core swap).
    resume_q = "How did you train YOLO for your computer vision project?"
    kept = _naturalize_static_question(
        "nlp_speech_ai",
        resume_q,
        variety_seed=0,
        replace_with_core=False,
    )
    assert "yolo" in kept.lower()
    assert "organize the code" not in kept.lower()


def test_soft_domain_redirect():
    r = domain_relevance_redirect_response(
        "How would you handle missing values before training?",
        attempt=1,
    )
    assert "missing values" in r.lower()
    assert "Please answer this directly" not in r


def test_soft_intent_redirects():
    repeat = intent_redirect_response("REPEAT_REQUEST", "", "How do you preprocess data?")
    assert "Happy to repeat" in repeat
    assert "preprocess" in repeat.lower()
    assert repeat.lower().count("preprocess") == 1

    off = intent_redirect_response(
        "OFF_TOPIC", "weather", "How do you preprocess data?"
    )
    assert "preprocess" in off.lower()
    # Bounded recovery: one ask, no stacked wrappers from prior TTS history.
    assert off.lower().count("how do you preprocess data") <= 1


if __name__ == "__main__":
    test_naturalize_seed0_has_no_lets_talk_frame()
    test_naturalize_rotates_openers()
    test_soft_domain_redirect()
    test_soft_intent_redirects()
    print("[PASS] test_phase6_natural_conversation")
