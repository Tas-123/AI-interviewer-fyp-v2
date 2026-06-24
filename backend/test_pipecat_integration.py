"""
test_pipecat_integration.py — Dry-run/mock tests for the Pipecat Voice Integration components.
Validates the custom FrameProcessor, session management, fallbacks, and lifecycle.
Does NOT require a real Pipecat installation or any external LLM/Gemini API calls.
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock

# Ensure backend directory is in path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from pipecat_integration.interview_processor import (
    InterviewProcessor,
    FrameDirection,
    TranscriptionFrame,
    TextFrame,
    EndTaskFrame,
    TTSSpeakFrame,
    sanitize_tts_text
)
from integration.dialogue_adapter import InterviewDialogueAdapter

class TestProcessor(InterviewProcessor):
    """
    Subclass of InterviewProcessor that captures pushed frames for easy assertions in unit tests.
    """
    def __init__(self, adapter, session_id):
        super().__init__(adapter, session_id)
        self.pushed_frames = []

    async def push_frame(self, frame, direction):
        self.pushed_frames.append((frame, direction))

def run_async_test(coro):
    """Helper to run async test coroutines."""
    return asyncio.run(coro)

async def test_processor_normal_turn():
    """Verify that TranscriptionFrame text is processed by adapter and AI response is pushed downstream."""
    mock_adapter = MagicMock()
    mock_adapter.process_user_text.return_value = {
        "session_id": "test-session",
        "ai_response_text": "That sounds very interesting. How did you implement that?",
        "current_state": "technical",
        "is_complete": False,
        "error": None
    }

    processor = TestProcessor(mock_adapter, "test-session")
    frame = TranscriptionFrame(text="I built a microservice using Python.", user_id="test-user", timestamp="0", finalized=True)
    
    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)

    # Verify adapter was called with correct parameters
    mock_adapter.process_user_text.assert_called_once_with("test-session", "I built a microservice using Python.")

    # Verify response frame was pushed downstream
    assert len(processor.pushed_frames) == 1
    pushed_frame, direction = processor.pushed_frames[0]
    assert isinstance(pushed_frame, TTSSpeakFrame)
    assert pushed_frame.text == "That sounds very interesting. How did you implement that?"
    assert direction == FrameDirection.DOWNSTREAM
    print("[PASS] test_processor_normal_turn")

async def test_processor_empty_transcript():
    """Verify that an empty/whitespace transcription frame is handled safely and pushes clarification prompt."""
    mock_adapter = MagicMock()
    processor = TestProcessor(mock_adapter, "test-session")
    frame = TranscriptionFrame(text="   ", user_id="test-user", timestamp="0", finalized=True)

    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)

    # Adapter should NOT be called to avoid wasting resources on blank transcriptions
    mock_adapter.process_user_text.assert_not_called()

    # Clarification frame should be pushed downstream
    assert len(processor.pushed_frames) == 1
    pushed_frame, direction = processor.pushed_frames[0]
    assert isinstance(pushed_frame, TTSSpeakFrame)
    assert "didn't catch that" in pushed_frame.text
    assert direction == FrameDirection.DOWNSTREAM
    print("[PASS] test_processor_empty_transcript")

async def test_processor_adapter_error_fallback():
    """Verify that if the dialogue adapter returns an error, a short fallback message is spoken."""
    mock_adapter = MagicMock()
    mock_adapter.process_user_text.return_value = {
        "session_id": "test-session",
        "ai_response_text": "",
        "current_state": "technical",
        "is_complete": False,
        "error": "Gemini API Timeout"
    }

    processor = TestProcessor(mock_adapter, "test-session")
    frame = TranscriptionFrame(text="My answer details", user_id="test-user", timestamp="0", finalized=True)

    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)

    # Verify fallback message was pushed downstream
    assert len(processor.pushed_frames) == 1
    pushed_frame, direction = processor.pushed_frames[0]
    assert isinstance(pushed_frame, TTSSpeakFrame)
    assert "trouble processing" in pushed_frame.text or "repeat" in pushed_frame.text
    assert direction == FrameDirection.DOWNSTREAM
    print("[PASS] test_processor_adapter_error_fallback")

async def test_processor_interview_completion():
    """Verify that when adapter marks interview as complete, closing message is spoken and EndTaskFrame is queued upstream."""
    mock_adapter = MagicMock()
    mock_adapter.process_user_text.return_value = {
        "session_id": "test-session",
        "ai_response_text": "Thank you, this concludes the interview. Goodbye!",
        "current_state": "wrapup",
        "is_complete": True,
        "error": None
    }

    processor = TestProcessor(mock_adapter, "test-session")
    frame = TranscriptionFrame(text="I am ready to wrap up.", user_id="test-user", timestamp="0", finalized=True)

    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)

    # Verify two frames were pushed: TTSSpeakFrame downstream and EndTaskFrame upstream
    assert len(processor.pushed_frames) == 2
    
    # 1. TTSSpeakFrame downstream
    pushed_frame_1, direction_1 = processor.pushed_frames[0]
    assert isinstance(pushed_frame_1, TTSSpeakFrame)
    assert pushed_frame_1.text == "Thank you, this concludes the interview. Goodbye!"
    assert direction_1 == FrameDirection.DOWNSTREAM

    # 2. EndTaskFrame upstream
    pushed_frame_2, direction_2 = processor.pushed_frames[1]
    assert isinstance(pushed_frame_2, EndTaskFrame)
    assert direction_2 == FrameDirection.UPSTREAM
    print("[PASS] test_processor_interview_completion")

async def test_session_lifecycle():
    """Verify standard session lifecycle: starts session, runs turns, ends session, checks database persistence."""
    adapter = InterviewDialogueAdapter()
    profile = {
        "name": "Jane QA",
        "role": "QA Engineer",
        "skills": ["Selenium", "Pytest"],
        "experience": "2 years"
    }

    # Mock dialogue manager components to prevent network dependency
    mock_dm = MagicMock()
    mock_dm.handle_turn.side_effect = [
        {"question": "Welcome! Tell me about your Pytest experience."}, # Start
        {"question": "How do you write a parameterized test in Pytest?"}, # Turn 1
        {"question": "Excellent. We will conclude here.", "evaluation": {"overall_score": 5.0}} # Turn 2
    ]
    mock_dm.get_status.side_effect = [
        {"state": "intro", "turn_count": 0},
        {"state": "technical", "turn_count": 1},
        {"state": "wrapup", "turn_count": 2}
    ]
    mock_dm.get_final_report.return_value = {
        "weighted_score_summary": {"avg_weighted_overall": 4.8},
        "consistency_rating": {"consistency_rating": "High"},
        "trend_label": "Improving"
    }

    # Apply mocks
    from unittest.mock import patch
    with patch("integration.dialogue_adapter.DialogueManager", return_value=mock_dm), \
         patch("integration.dialogue_adapter.db.save_session") as mock_save:
         
        # 1. Start Interview
        start_res = adapter.start_interview(profile)
        session_id = start_res["session_id"]
        assert session_id != ""
        assert start_res["ai_response_text"] == "Welcome! Tell me about your Pytest experience."
        assert start_res["is_complete"] == False
        assert mock_save.called

        # 2. Setup Processor and simulate turn 1
        processor = TestProcessor(adapter, session_id)
        await processor.process_frame(TranscriptionFrame(text="I use pytest fixtures for setting up database state.", user_id="test-user", timestamp="0", finalized=True), FrameDirection.DOWNSTREAM)
        
        assert len(processor.pushed_frames) == 1
        p1, d1 = processor.pushed_frames[0]
        assert isinstance(p1, TTSSpeakFrame)
        assert p1.text == "How do you write a parameterized test in Pytest?"
        
        # 3. Simulate turn 2 (completes)
        # Force next get_status to return wrapup state so adapter recognizes it is complete
        mock_dm.get_status.return_value = {"state": "wrapup", "turn_count": 2}
        await processor.process_frame(TranscriptionFrame(text="You use pytest mark parameterize decorator.", user_id="test-user", timestamp="0", finalized=True), FrameDirection.DOWNSTREAM)
        
        # Pushed goodbye TTSSpeakFrame + EndTaskFrame
        assert len(processor.pushed_frames) == 3
        p2, d2 = processor.pushed_frames[1]
        assert isinstance(p2, TTSSpeakFrame)
        assert p2.text == "Excellent. We will conclude here."
        p3, d3 = processor.pushed_frames[2]
        assert isinstance(p3, EndTaskFrame)

        # 4. End Interview
        end_res = adapter.end_interview(session_id)
        assert end_res["status"] == "ended"
        assert session_id not in adapter.sessions

    print("[PASS] test_session_lifecycle")

async def test_sanitize_tts_text():
    """Verify that sanitize_tts_text correctly substitutes Gemini error strings with a greeting fallback."""
    # Standard greeting remains unchanged
    normal_text = "Hello, please tell me about yourself."
    assert sanitize_tts_text(normal_text) == normal_text

    # Quota/Gemini errors get substituted
    error_1 = "[Error generating question. Please try again.]"
    error_2 = "Error generating question: API key invalid."
    fallback = "Welcome to the interview. Please tell me about yourself and your experience with Python."
    
    assert sanitize_tts_text(error_1) == fallback
    assert sanitize_tts_text(error_2) == fallback
    print("[PASS] test_sanitize_tts_text")

def main():
    print("=" * 60)
    print("PIPECAT VOICE LAYER INTEGRATION - DRY-RUN TEST SUITE")
    print("=" * 60)
    print()

    tests = [
        test_processor_normal_turn,
        test_processor_empty_transcript,
        test_processor_adapter_error_fallback,
        test_processor_interview_completion,
        test_session_lifecycle,
        test_sanitize_tts_text
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            run_async_test(test())
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

if __name__ == "__main__":
    main()
