"""
test_dialogue_adapter.py — Focused tests for the InterviewDialogueAdapter.
No external LLM API calls required.
"""

import sys
import os

os.environ.setdefault("GROQ_API_KEY", "mock-key-123")

from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from integration.dialogue_adapter import InterviewDialogueAdapter
from core.session_service import InterviewSession, reset_session_service


def _mock_service():
    return MagicMock()


def test_adapter_start_interview():
    """Verify that start_interview initializes a session and generates greeting."""
    svc = _mock_service()
    mock_dm = MagicMock()
    svc.start_interview.return_value = (
        "sess-1",
        {"question": "Hello, welcome to your interview!"},
    )
    svc.get_dialogue_manager.return_value = mock_dm
    mock_dm.get_status.return_value = {
        "state": "intro",
        "turn_count": 0,
        "evaluation_summary": None,
    }

    adapter = InterviewDialogueAdapter(session_service=svc)
    profile = {"skills": ["Python"], "experience": "3 years"}
    res = adapter.start_interview(profile)

    assert res["session_id"] == "sess-1"
    assert res["ai_response_text"] == "Hello, welcome to your interview!"
    assert res["current_state"] == "intro"
    assert res["turn_count"] == 0
    assert res["is_complete"] is False
    assert res["error"] is None
    svc.start_interview.assert_called_once_with(profile)
    print("[PASS] test_adapter_start_interview")


def test_adapter_process_user_text():
    """Verify that process_user_text calls SessionService and returns correct response."""
    svc = _mock_service()
    svc.has.return_value = True
    svc.process_turn.return_value = {
        "question": "Can you explain inheritance in Python?",
        "evaluation": {
            "overall_score": 4.0,
            "weighted_overall_score": 4.2,
            "weakest_dimension": "clarity",
            "hire_signal": "Hire",
        },
    }
    svc.get_status.return_value = {
        "state": "technical",
        "turn_count": 2,
        "evaluation_summary": {"overall_score": 4.0},
    }

    adapter = InterviewDialogueAdapter(session_service=svc)
    res = adapter.process_user_text(
        "test-session", "I have used Python inheritance in Django models."
    )

    assert res["session_id"] == "test-session"
    assert res["ai_response_text"] == "Can you explain inheritance in Python?"
    assert res["current_state"] == "technical"
    assert res["turn_count"] == 2
    assert res["is_complete"] is False
    assert res["error"] is None
    assert res["evaluation_summary"]["overall_score"] == 4.0
    svc.process_turn.assert_called_once_with(
        "test-session", "I have used Python inheritance in Django models."
    )
    print("[PASS] test_adapter_process_user_text")


def test_adapter_preserves_session_state():
    """Verify sequential turns through real SessionService + mocked LLM."""
    from unittest.mock import patch

    reset_session_service()
    adapter = InterviewDialogueAdapter()
    profile = {"skills": ["Python"], "experience": "3 years"}

    with patch("dialogue.evaluator.Evaluator.adaptive_evaluate") as mock_eval:
        mock_eval.side_effect = [
            {
                "evaluation": {
                    "overall_score": 4.0,
                    "weighted_overall_score": 4.0,
                    "weakest_dimension": "structure",
                    "hire_signal": "Hire",
                    "clarity_score": 4,
                    "structure_score": 4,
                    "confidence_score": 4,
                    "ownership_score": 4,
                    "leadership_score": 4,
                    "result_score": 4,
                    "clarity": 4,
                    "structure": 4,
                    "confidence": 4,
                    "ownership": 4,
                    "leadership": 4,
                    "result_orientation": 4,
                },
                "decision": {
                    "type": "ADVANCE",
                    "next_question": "Explain python list comprehensions.",
                },
                "latency_ms": 120,
            },
            {
                "evaluation": {
                    "overall_score": 4.0,
                    "weighted_overall_score": 4.0,
                    "weakest_dimension": "structure",
                    "hire_signal": "Hire",
                    "clarity_score": 4,
                    "structure_score": 4,
                    "confidence_score": 4,
                    "ownership_score": 4,
                    "leadership_score": 4,
                    "result_score": 4,
                    "clarity": 4,
                    "structure": 4,
                    "confidence": 4,
                    "ownership": 4,
                    "leadership": 4,
                    "result_orientation": 4,
                },
                "decision": {
                    "type": "ADVANCE",
                    "next_question": "Tell me about a time you resolved a conflict.",
                },
                "latency_ms": 130,
            },
        ]
        with patch(
            "dialogue.llm_adapter.LLMAdapter._call_llm",
            return_value="Mocked LLM Response",
        ), patch(
            "dialogue.dialogue_manager.DialogueManager._is_answer_relevant_to_question",
            return_value=True,
        ):
            start_res = adapter.start_interview(profile)
            session_id = start_res["session_id"]
            assert start_res["current_state"] == "technical"
            assert start_res["turn_count"] == 1
            assert start_res["ai_response_text"] == "Mocked LLM Response"

            res1 = adapter.process_user_text(
                session_id, "I have been writing Python scripts for 3 years."
            )
            assert res1["current_state"] == "technical"
            assert res1["turn_count"] == 2
            assert "Python project structure" in res1["ai_response_text"]

            res2 = adapter.process_user_text(
                session_id, "They are syntax short-cuts for generating lists."
            )
            assert res2["current_state"] == "technical"
            assert res2["turn_count"] == 3
            assert "overfitting" in res2["ai_response_text"]

    reset_session_service()
    print("[PASS] test_adapter_preserves_session_state")


def test_adapter_empty_transcript_handling():
    """Verify empty/None transcript is handled safely."""
    svc = _mock_service()
    svc.has.return_value = True
    svc.process_turn.return_value = {"question": "Next question?"}
    svc.get_status.return_value = {"state": "technical", "turn_count": 3}

    adapter = InterviewDialogueAdapter(session_service=svc)
    res = adapter.process_user_text("test-session", "")
    assert res["error"] is None
    svc.process_turn.assert_called_with("test-session", "")

    res = adapter.process_user_text("test-session", None)
    assert res["error"] is None
    print("[PASS] test_adapter_empty_transcript_handling")


def test_adapter_invalid_session_safety():
    """Invalid session IDs return safe error dicts."""
    svc = _mock_service()
    svc.has.return_value = False
    svc.end_session.return_value = {
        "session_id": "non-existent-id",
        "status": "not_found",
        "final_report": None,
        "error": "Session ID 'non-existent-id' not found.",
    }

    adapter = InterviewDialogueAdapter(session_service=svc)
    res = adapter.process_user_text("non-existent-id", "some answer")
    assert res["error"] is not None
    assert res["is_complete"] is True

    report_res = adapter.get_report("non-existent-id")
    assert "error" in report_res

    end_res = adapter.end_interview("non-existent-id")
    assert end_res["status"] == "not_found"
    print("[PASS] test_adapter_invalid_session_safety")


def test_adapter_get_report_and_end():
    """Final report retrieval and session end."""
    svc = _mock_service()
    svc.has.return_value = True
    svc.get_report.return_value = {
        "weighted_score_summary": {"avg_weighted_overall": 4.2},
        "consistency_rating": {"consistency_rating": "High"},
    }
    svc.end_session.return_value = {
        "session_id": "test-session",
        "status": "ended",
        "final_report": {"ok": True},
        "error": None,
    }

    adapter = InterviewDialogueAdapter(session_service=svc)
    report = adapter.get_report("test-session")
    assert report["weighted_score_summary"]["avg_weighted_overall"] == 4.2

    end_res = adapter.end_interview("test-session")
    assert end_res["status"] == "ended"
    svc.end_session.assert_called_once_with("test-session", remove=True)
    print("[PASS] test_adapter_get_report_and_end")


def test_adapter_error_handling_grace():
    """Exceptions from SessionService are caught gracefully."""
    svc = _mock_service()
    svc.has.return_value = True
    svc.process_turn.side_effect = RuntimeError("Groq API call timed out")
    mock_session = MagicMock()
    mock_session.dialogue_manager.context.state.value = "technical"
    mock_session.dialogue_manager.context.turn_count = 3
    svc.get.return_value = mock_session

    adapter = InterviewDialogueAdapter(session_service=svc)
    res = adapter.process_user_text("test-session", "my answer")

    assert res["error"] == "Groq API call timed out"
    assert res["ai_response_text"] == ""
    assert res["is_complete"] is False
    print("[PASS] test_adapter_error_handling_grace")


if __name__ == "__main__":
    print("=" * 60)
    print("INTERVIEW DIALOGUE ADAPTER TEST SUITE")
    print("=" * 60)
    print()

    tests = [
        test_adapter_start_interview,
        test_adapter_process_user_text,
        test_adapter_preserves_session_state,
        test_adapter_empty_transcript_handling,
        test_adapter_invalid_session_safety,
        test_adapter_get_report_and_end,
        test_adapter_error_handling_grace,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__} ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    sys.exit(1 if failed else 0)
