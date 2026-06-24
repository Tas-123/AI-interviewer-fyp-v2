"""
test_dialogue_adapter.py — Focused tests for the InterviewDialogueAdapter.
No external LLM or Gemini API calls required.
"""

import sys
import os

# Set environment variables before imports to prevent LLM config errors
os.environ["GEMINI_API_KEY"] = "mock-key-123"

from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from integration.dialogue_adapter import InterviewDialogueAdapter
from dialogue.states import InterviewState
from dialogue.context import InterviewContext

def test_adapter_start_interview():
    """Verify that start_interview initializes a session and generates greeting."""
    adapter = InterviewDialogueAdapter()
    profile = {"skills": ["Python"], "experience": "3 years"}
    
    # Mock DialogueManager methods to avoid real LLM calls
    with patch("integration.dialogue_adapter.DialogueManager") as mock_dm_class:
        mock_dm = MagicMock()
        mock_dm.handle_turn.return_value = {"question": "Hello, welcome to your interview!"}
        mock_dm.get_status.return_value = {
            "state": "intro",
            "turn_count": 0,
            "evaluation_summary": None
        }
        mock_dm_class.return_value = mock_dm
        
        with patch("integration.dialogue_adapter.db.save_session") as mock_save:
            res = adapter.start_interview(profile)
            
            # Assertions
            assert res["session_id"] != ""
            assert res["ai_response_text"] == "Hello, welcome to your interview!"
            assert res["current_state"] == "intro"
            assert res["turn_count"] == 0
            assert res["is_complete"] == False
            assert res["error"] is None
            
            # Check session registry
            assert res["session_id"] in adapter.sessions
            assert mock_save.called
            print("[PASS] test_adapter_start_interview")

def test_adapter_process_user_text():
    """Verify that process_user_text calls DialogueManager and returns correct response."""
    adapter = InterviewDialogueAdapter()
    session_id = "test-session"
    
    mock_dm = MagicMock()
    mock_dm.handle_turn.return_value = {
        "question": "Can you explain inheritance in Python?",
        "evaluation": {
            "overall_score": 4.0,
            "weighted_overall_score": 4.2,
            "weakest_dimension": "clarity",
            "hire_signal": "Hire"
        }
    }
    mock_dm.get_status.return_value = {
        "state": "technical",
        "turn_count": 2,
        "evaluation_summary": {"overall_score": 4.0}
    }
    adapter.sessions[session_id] = mock_dm
    
    res = adapter.process_user_text(session_id, "I have used Python inheritance in Django models.")
    
    assert res["session_id"] == session_id
    assert res["ai_response_text"] == "Can you explain inheritance in Python?"
    assert res["current_state"] == "technical"
    assert res["turn_count"] == 2
    assert res["is_complete"] == False
    assert res["error"] is None
    assert res["evaluation_summary"] is not None
    assert res["evaluation_summary"]["overall_score"] == 4.0
    assert res["evaluation_summary"]["weighted_score"] == 4.2
    assert res["evaluation_summary"]["weakest_dimension"] == "clarity"
    assert res["evaluation_summary"]["hire_signal"] == "Hire"
    
    mock_dm.handle_turn.assert_called_with("I have used Python inheritance in Django models.")
    print("[PASS] test_adapter_process_user_text")

def test_adapter_preserves_session_state():
    """Verify that state and turn count increments correctly on sequential turns."""
    adapter = InterviewDialogueAdapter()
    profile = {"skills": ["Python"], "experience": "3 years"}
    
    # We will use real DialogueManager components but mock the Evaluator/LLMAdapter to keep it hermetic
    with patch("dialogue.evaluator.Evaluator.adaptive_evaluate") as mock_eval:
        mock_eval.side_effect = [
            {
                "evaluation": {
                    "overall_score": 4.0,
                    "weighted_overall_score": 4.0,
                    "weakest_dimension": "structure",
                    "hire_signal": "Hire",
                    "clarity_score": 4, "structure_score": 4, "confidence_score": 4,
                    "ownership_score": 4, "leadership_score": 4, "result_score": 4,
                    "clarity": 4, "structure": 4, "confidence": 4,
                    "ownership": 4, "leadership": 4, "result_orientation": 4
                },
                "decision": {
                    "type": "ADVANCE",
                    "next_question": "Explain python list comprehensions."
                },
                "latency_ms": 120
            },
            {
                "evaluation": {
                    "overall_score": 4.0,
                    "weighted_overall_score": 4.0,
                    "weakest_dimension": "structure",
                    "hire_signal": "Hire",
                    "clarity_score": 4, "structure_score": 4, "confidence_score": 4,
                    "ownership_score": 4, "leadership_score": 4, "result_score": 4,
                    "clarity": 4, "structure": 4, "confidence": 4,
                    "ownership": 4, "leadership": 4, "result_orientation": 4
                },
                "decision": {
                    "type": "ADVANCE",
                    "next_question": "Tell me about a time you resolved a conflict."
                },
                "latency_ms": 130
            }
        ]
        
        with patch("dialogue.llm_adapter.LLMAdapter._call_llm", return_value="Mocked LLM Response") as mock_call, \
             patch("dialogue.dialogue_manager.DialogueManager._is_answer_relevant_to_question", return_value=True):
            
            # Start
            start_res = adapter.start_interview(profile)
            session_id = start_res["session_id"]
            assert start_res["current_state"] == "technical"
            assert start_res["turn_count"] == 1  # turn_count is 1 after greeting turn is recorded
            assert start_res["ai_response_text"] == "Mocked LLM Response"
            
            # Turn 1
            res1 = adapter.process_user_text(session_id, "I have been writing Python scripts for 3 years.")
            assert res1["current_state"] == "technical"
            assert res1["turn_count"] == 2
            assert "Python project structure" in res1["ai_response_text"]
            
            # Turn 2
            res2 = adapter.process_user_text(session_id, "They are syntax short-cuts for generating lists.")
            assert res2["current_state"] == "technical"
            assert res2["turn_count"] == 3
            assert "overfitting" in res2["ai_response_text"]
            
            print("[PASS] test_adapter_preserves_session_state")

def test_adapter_empty_transcript_handling():
    """Verify that an empty or None transcript is handled safely without throwing errors."""
    adapter = InterviewDialogueAdapter()
    session_id = "test-session"
    
    mock_dm = MagicMock()
    mock_dm.handle_turn.return_value = {"question": "Next question?"}
    mock_dm.get_status.return_value = {"state": "technical", "turn_count": 3}
    adapter.sessions[session_id] = mock_dm
    
    # Passing empty string
    res = adapter.process_user_text(session_id, "")
    assert res["error"] is None
    assert res["ai_response_text"] == "Next question?"
    mock_dm.handle_turn.assert_called_with("")
    
    # Passing None
    res = adapter.process_user_text(session_id, None)
    assert res["error"] is None
    assert res["ai_response_text"] == "Next question?"
    mock_dm.handle_turn.assert_called_with("")
    
    print("[PASS] test_adapter_empty_transcript_handling")

def test_adapter_invalid_session_safety():
    """Verify that invalid session IDs return safe error dictionaries without throwing exceptions."""
    adapter = InterviewDialogueAdapter()
    
    # Non-existent session id
    res = adapter.process_user_text("non-existent-id", "some answer")
    assert "error" in res
    assert res["error"] is not None
    assert res["is_complete"] == True
    assert res["ai_response_text"] == ""
    
    report_res = adapter.get_report("non-existent-id")
    assert "error" in report_res
    
    end_res = adapter.end_interview("non-existent-id")
    assert "error" in end_res
    assert end_res["status"] == "not_found"
    
    print("[PASS] test_adapter_invalid_session_safety")

def test_adapter_get_report_and_end():
    """Verify that final report can be retrieved and interview ended successfully."""
    adapter = InterviewDialogueAdapter()
    session_id = "test-session"
    
    mock_dm = MagicMock()
    mock_dm.get_final_report.return_value = {
        "weighted_score_summary": {"avg_weighted_overall": 4.2},
        "consistency_rating": {"consistency_rating": "High"}
    }
    adapter.sessions[session_id] = mock_dm
    
    # Test get_report
    report = adapter.get_report(session_id)
    assert report["weighted_score_summary"]["avg_weighted_overall"] == 4.2
    
    # Test end_interview
    end_res = adapter.end_interview(session_id)
    assert end_res["session_id"] == session_id
    assert end_res["status"] == "ended"
    assert end_res["error"] is None
    
    # Session should be popped from memory store
    assert session_id not in adapter.sessions
    
    print("[PASS] test_adapter_get_report_and_end")

def test_adapter_error_handling_grace():
    """Verify that exceptions raised by DialogueManager are caught gracefully by the adapter."""
    adapter = InterviewDialogueAdapter()
    session_id = "test-session"
    
    mock_dm = MagicMock()
    # Force handle_turn to raise an exception (like LLM timeout or credential error)
    mock_dm.handle_turn.side_effect = RuntimeError("Gemini API call timed out")
    mock_dm.context.state.value = "technical"
    mock_dm.context.turn_count = 3
    adapter.sessions[session_id] = mock_dm
    
    res = adapter.process_user_text(session_id, "my answer")
    
    # Assertions for error response
    assert res["session_id"] == session_id
    assert res["error"] == "Gemini API call timed out"
    assert res["ai_response_text"] == ""
    assert res["is_complete"] == False
    assert res["current_state"] == "technical"
    assert res["turn_count"] == 3
    
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
    
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)
