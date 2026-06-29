import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.followup_policy import FOLLOWUP_ADVANCE, classify_followup_type


def test_advance_on_sufficient_answer():
    ft, reason = classify_followup_type(
        {"weakest_dimension": "clarity", "weighted_overall_score": 4.0},
        {"type": "ADVANCE"},
        answer_word_count=25,
        engine_reason="",
    )
    assert ft == FOLLOWUP_ADVANCE
    assert "advancing" in reason.lower()


if __name__ == "__main__":
    test_advance_on_sufficient_answer()
    print("[PASS] test_followup_policy")
