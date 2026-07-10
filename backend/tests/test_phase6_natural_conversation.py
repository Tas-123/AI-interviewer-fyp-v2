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
    a = _naturalize_static_question("python", "x", variety_seed=0)
    b = _naturalize_static_question("python", "x", variety_seed=1)
    c = _naturalize_static_question("python", "x", variety_seed=2)
    assert a != b or b != c
    assert "organize the code" in a.lower()
    assert "organize the code" in b.lower()
    # Core ask identical after stripping openers
    assert a.endswith("debug?") or "easy to debug" in a.lower()


def test_soft_domain_redirect():
    r = domain_relevance_redirect_response(
        "How would you handle missing values before training?",
        attempt=1,
    )
    assert "missing values" in r.lower()
    assert "Please answer this directly" not in r


def test_soft_intent_redirects():
    assert intent_redirect_response("REPEAT_REQUEST", "", "Q?").startswith(
        "Happy to repeat"
    )
    assert "We'll stay on the interview" in intent_redirect_response(
        "OFF_TOPIC", "weather", "How do you preprocess data?"
    )


if __name__ == "__main__":
    test_naturalize_seed0_has_no_lets_talk_frame()
    test_naturalize_rotates_openers()
    test_soft_domain_redirect()
    test_soft_intent_redirects()
    print("[PASS] test_phase6_natural_conversation")
