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
from voice.voice_turn_policy import VoiceTurnPolicy, DEFAULT_FILLER_WORDS
from integration.dialogue_adapter import InterviewDialogueAdapter

class TestProcessor(InterviewProcessor):
    """
    Subclass of InterviewProcessor that captures pushed frames for easy assertions in unit tests.
    """
    def __init__(self, adapter, session_id):
        test_policy = VoiceTurnPolicy(
            transcript_debounce_seconds=0,
            short_answer_grace_seconds=0,
            short_answer_word_threshold=6,
            startup_audio_gate_seconds=0,
            startup_refresh_seconds=0,
            bot_echo_cooldown_seconds=0,
            bot_stop_echo_cooldown_seconds=0,
            closing_delay_seconds=0,
            candidate_silence_nudge_seconds=0,
            candidate_silence_rephrase_seconds=0,
            barge_in_min_bot_speak_seconds=0,
            final_transcript_debounce_seconds=0,
            filler_words=DEFAULT_FILLER_WORDS,
        )
        super().__init__(adapter, session_id, policy=test_policy)
        self.pushed_frames = []
        self.reset_for_new_session()

    async def push_frame(self, frame, direction):
        self.pushed_frames.append((frame, direction))

async def _flush_processor(processor):
    """Wait for scheduled debounce / turn tasks in tests."""
    if processor._debounce_task and not processor._debounce_task.done():
        await processor._debounce_task
    if processor._interim_finalize_task and not processor._interim_finalize_task.done():
        await processor._interim_finalize_task

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
    await _flush_processor(processor)

    # Verify adapter was called with correct parameters
    mock_adapter.process_user_text.assert_called_once_with("test-session", "I built a microservice using Python.")

    # Verify response frame was pushed downstream
    tts_frames = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert len(tts_frames) == 1
    assert tts_frames[0].text == "That sounds very interesting. How did you implement that?"
    print("[PASS] test_processor_normal_turn")

async def test_processor_empty_transcript():
    """Verify that an empty/whitespace transcription frame is handled safely and pushes clarification prompt."""
    mock_adapter = MagicMock()
    processor = TestProcessor(mock_adapter, "test-session")
    frame = TranscriptionFrame(text="   ", user_id="test-user", timestamp="0", finalized=True)

    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)
    await _flush_processor(processor)

    # Adapter should NOT be called to avoid wasting resources on blank transcriptions
    mock_adapter.process_user_text.assert_not_called()

    # Clarification frame should be pushed downstream
    tts_frames = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert len(tts_frames) == 1
    assert "didn't catch that" in tts_frames[0].text
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
    await _flush_processor(processor)

    # Verify fallback message was pushed downstream
    tts_frames = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert len(tts_frames) == 1
    assert "trouble processing" in tts_frames[0].text or "repeat" in tts_frames[0].text
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
    await _flush_processor(processor)

    # Verify AI closing is spoken once (duplicate system closing suppressed when
    # ai_response already contains "concludes the interview") and EndTaskFrame upstream.
    tts_frames = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
    end_frames = [f for f, d in processor.pushed_frames if isinstance(f, EndTaskFrame)]
    assert len(tts_frames) == 1
    assert tts_frames[0].text == "Thank you, this concludes the interview. Goodbye!"
    assert len(end_frames) == 1
    assert processor.pushed_frames[-1][1] == FrameDirection.UPSTREAM
    print("[PASS] test_processor_interview_completion")

async def test_session_lifecycle():
    """Verify standard session lifecycle: starts session, runs turns, ends session, checks database persistence."""
    from core.session_service import reset_session_service
    reset_session_service()
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
    with patch("core.session_service.DialogueManager", return_value=mock_dm), \
         patch("core.session_service.db.save_session") as mock_save:
         
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
        await _flush_processor(processor)
        
        tts_frames = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
        assert len(tts_frames) == 1
        assert tts_frames[0].text == "How do you write a parameterized test in Pytest?"
        
        # 3. Simulate turn 2 (completes)
        # Force next get_status to return wrapup state so adapter recognizes it is complete
        mock_dm.get_status.return_value = {"state": "wrapup", "turn_count": 2}
        await processor.process_frame(TranscriptionFrame(text="You use pytest mark parameterize decorator.", user_id="test-user", timestamp="0", finalized=True), FrameDirection.DOWNSTREAM)
        await _flush_processor(processor)
        
        tts_frames = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
        end_frames = [f for f, d in processor.pushed_frames if isinstance(f, EndTaskFrame)]
        assert len(tts_frames) == 3
        assert tts_frames[1].text == "Excellent. We will conclude here."
        assert len(end_frames) == 1

        # 4. End Interview
        end_res = adapter.end_interview(session_id)
        assert end_res["status"] == "ended"
        assert not adapter._sessions.has(session_id)

    print("[PASS] test_session_lifecycle")

async def test_sanitize_tts_text():
    """Verify that sanitize_tts_text correctly substitutes Gemini error strings with a greeting fallback."""
    # Standard greeting remains unchanged
    normal_text = "Hello, please tell me about yourself."
    assert sanitize_tts_text(normal_text) == normal_text

    # Quota/Gemini errors get substituted
    error_1 = "[Error generating question. Please try again.]"
    error_2 = "Error generating question: API key invalid."
    fallback = "Welcome to the interview. Please briefly introduce yourself and tell me what kind of role or area you would like this interview to focus on."
    
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
