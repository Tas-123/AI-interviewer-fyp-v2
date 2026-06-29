import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.guards.echo_guard import looks_like_bot_question_echo


def test_intro_echo_detected():
    intro_q = (
        "Good morning, welcome to the interview for the AI Engineer position. "
        "Can you start by introducing yourself?"
    )
    assert looks_like_bot_question_echo(intro_q, intro_q) is True


def test_real_answer_not_echo():
    overfit_q = (
        "Suppose your training score is high but validation performance drops. "
        "How would you detect overfitting?"
    )
    real_answer = (
        "I detect overfitting by comparing the gap between training and validation "
        "performance. I would use regularization and early stopping."
    )
    assert looks_like_bot_question_echo(real_answer, overfit_q) is False


if __name__ == "__main__":
    test_intro_echo_detected()
    test_real_answer_not_echo()
    print("[PASS] test_echo_guard")
