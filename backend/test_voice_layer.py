"""
test_voice_layer.py — Offline tests for the Voice Conversation Infrastructure.

Tests run without LLM, DB, or network dependencies. Validates:
  1. Voice session creation + retrieval
  2. Session expiry
  3. Session close + active count
  4. VAD simulator end-of-turn detection
  5. Transcript buffer accumulation
  6. Barge-in detection
  7. Context guard off-topic detection
  8. Streaming response chunking
  9. Compact evaluation helper
  10. Interruption manager combined check
  11. Session listing

Uses mock for DialogueManager to avoid google.generativeai dependency.
"""

import os
import sys
import time
import types
import unittest.mock as mock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# ── Set dummy API key so Evaluator.__init__ doesn't raise ────────
os.environ.setdefault("GROQ_API_KEY", "test-dummy-key-not-real")

# ── Mock the google.generativeai module before any imports ───────
# This prevents the transitive import of google.generativeai through
# DialogueManager → Evaluator → genai
fake_genai = types.ModuleType("google.generativeai")
fake_genai.configure = lambda **kw: None
fake_genai.GenerativeModel = mock.MagicMock

fake_google = types.ModuleType("google")
fake_google.generativeai = fake_genai

sys.modules["google"] = fake_google
sys.modules["google.generativeai"] = fake_genai

# Now safe to import voice layer modules
from voice.voice_session_manager import VoiceSessionManager, SESSION_TIMEOUT_SECONDS
from voice.vad_simulator import VADSimulator
from voice.interruption_manager import InterruptionManager
from voice.streaming_response_handler import split_response_sync
from voice.conversation_orchestrator import _compact_eval


# ===================================================================
#  Test 1: Voice Session Creation
# ===================================================================

def test_session_creation():
    """VoiceSessionManager should create and retrieve sessions."""
    mgr = VoiceSessionManager()
    resume = {"skills": ["Python", "Django"], "role": "Backend Engineer"}

    session = mgr.create_session(resume_data=resume, session_id="test-voice-1")

    assert session.session_id == "test-voice-1"
    # Phase 3: target_role drives role title; resume personalizes skills
    assert session.candidate_role == "Junior AI Engineer"
    assert "Python" in session.candidate_skills
    assert session.profile_source == "resume"
    assert session.is_closed is False
    assert session.transcript_buffer == ""
    assert session.conversation_history == []

    # Retrieve
    found = mgr.get_session("test-voice-1")
    assert found is not None
    assert found.session_id == "test-voice-1"

    # Not found
    assert mgr.get_session("nonexistent") is None

    return True


# ===================================================================
#  Test 2: Session Expiry
# ===================================================================

def test_session_expiry():
    """Expired sessions should be cleaned up."""
    mgr = VoiceSessionManager()
    resume = {"skills": ["Java"]}

    session = mgr.create_session(resume_data=resume, session_id="expire-test")

    # Force the session to appear old
    session.last_activity = time.time() - SESSION_TIMEOUT_SECONDS - 10

    removed = mgr.cleanup_expired()
    assert removed == 1
    assert mgr.get_session("expire-test") is None

    return True


# ===================================================================
#  Test 3: Session Close and Count
# ===================================================================

def test_session_close():
    """Closed sessions should not be retrievable."""
    mgr = VoiceSessionManager()
    mgr.create_session(resume_data={"skills": []}, session_id="close-test")

    assert mgr.get_active_count() == 1

    mgr.close_session("close-test")
    assert mgr.get_session("close-test") is None
    assert mgr.get_active_count() == 0

    return True


# ===================================================================
#  Test 4: VAD Simulator End-of-Turn
# ===================================================================

def test_vad_speech_end():
    """VAD should detect speech_end as end of turn."""
    vad = VADSimulator()

    # Speech chunk
    result = vad.process_message({"type": "speech_chunk", "text": "hello"})
    assert result["is_end_of_turn"] is False
    assert result["is_speech"] is True
    assert result["text"] == "hello"

    # Speech end
    result = vad.process_message({"type": "speech_end"})
    assert result["is_end_of_turn"] is True
    assert result["is_speech"] is False

    # Unknown type
    result = vad.process_message({"type": "ping"})
    assert result["is_end_of_turn"] is False
    assert result["is_speech"] is False

    return True


# ===================================================================
#  Test 5: Transcript Buffer Accumulation
# ===================================================================

def test_transcript_buffer():
    """Transcript chunks should accumulate and flush correctly."""
    mgr = VoiceSessionManager()
    mgr.create_session(resume_data={"skills": []}, session_id="buffer-test")

    mgr.append_transcript_chunk("buffer-test", "I worked on")
    mgr.append_transcript_chunk("buffer-test", "a Django project")
    mgr.append_transcript_chunk("buffer-test", "for two years")

    transcript = mgr.flush_transcript("buffer-test")
    assert transcript == "I worked on a Django project for two years"

    # Buffer should be empty after flush
    assert mgr.flush_transcript("buffer-test") == ""

    return True


# ===================================================================
#  Test 6: Barge-In Detection
# ===================================================================

def test_barge_in():
    """Should detect rambling (too many words)."""
    im = InterruptionManager(barge_in_threshold=20)

    # Short answer - no barge-in
    result = im.check_barge_in("This is a short answer.")
    assert result is None

    # Long answer - barge-in triggered
    long_text = " ".join(["word"] * 25)
    result = im.check_barge_in(long_text)
    assert result is not None
    assert result["type"] == "interruption"
    assert result["reason"] == "barge_in"
    assert "message" in result
    assert result["word_count"] == 25

    return True


# ===================================================================
#  Test 7: Context Guard Off-Topic Detection
# ===================================================================

def test_context_guard():
    """Should detect off-topic answers."""
    im = InterruptionManager(similarity_threshold=0.08)

    # On-topic answer
    question = "Tell me about a leadership situation you handled."
    answer = ("I led a team of five engineers through a critical project. "
              "We had a tight deadline and I handled the leadership "
              "responsibilities by delegating tasks effectively.")
    result = im.check_context_guard(question, answer)
    assert result is None, f"Expected on-topic, got: {result}"

    # Off-topic answer
    question = "Tell me about a leadership situation you handled."
    answer = ("I enjoy playing cricket on weekends. "
              "My favorite movie is Inception and I like cooking pasta.")
    result = im.check_context_guard(question, answer)
    assert result is not None, "Expected off-topic detection"
    assert result["reason"] == "off_topic"

    # Short answer - skip check
    result = im.check_context_guard("Question?", "Yes.")
    assert result is None

    return True


# ===================================================================
#  Test 8: Streaming Response Chunking
# ===================================================================

def test_streaming_response():
    """Streaming handler should split text into correct chunks."""
    chunks = split_response_sync(
        "Hello welcome to the interview session today",
        chunk_size=3,
    )

    assert len(chunks) > 0
    assert all(c["type"] == "ai_response_chunk" for c in chunks)

    # Only last chunk should be final
    for c in chunks[:-1]:
        assert c["is_final"] is False
    assert chunks[-1]["is_final"] is True

    # Reconstruct full text
    reconstructed = " ".join(c["text"] for c in chunks)
    assert reconstructed == "Hello welcome to the interview session today"

    # Empty text
    empty_chunks = split_response_sync("")
    assert len(empty_chunks) == 1
    assert empty_chunks[0]["is_final"] is True

    return True


# ===================================================================
#  Test 9: Compact Evaluation Helper
# ===================================================================

def test_compact_eval():
    """Compact eval should extract key fields."""
    full_eval = {
        "clarity": 4, "structure": 3, "confidence": 4,
        "ownership": 3, "leadership": 2, "result_orientation": 3,
        "overall_score": 3.17, "weighted_overall_score": 3.05,
        "weakest_dimension": "leadership",
        "hire_signal": "Hire",
        "star_breakdown": {"situation_present": True},
    }

    compact = _compact_eval(full_eval)
    assert compact is not None
    assert compact["overall_score"] == 3.17
    assert compact["weighted_score"] == 3.05
    assert compact["weakest_dimension"] == "leadership"

    # None input
    assert _compact_eval(None) is None

    return True


# ===================================================================
#  Test 10: Interruption Manager Combined Check
# ===================================================================

def test_combined_interruption_check():
    """Combined check should return first triggered interruption."""
    im = InterruptionManager(barge_in_threshold=10, similarity_threshold=0.08)

    # Normal case — no interruption
    result = im.check_all("Tell me about leadership.", "I led a team.")
    assert result is None

    # Barge-in takes priority
    long_text = " ".join(["rambling"] * 15)
    result = im.check_all("Question?", long_text)
    assert result is not None
    assert result["reason"] == "barge_in"

    return True


# ===================================================================
#  Test 11: Session Listing
# ===================================================================

def test_session_listing():
    """Should list all sessions with correct metadata."""
    mgr = VoiceSessionManager()
    mgr.create_session(resume_data={"skills": ["Go"], "role": "SRE"}, session_id="s1")
    mgr.create_session(resume_data={"skills": ["Rust"], "role": "Dev"}, session_id="s2")

    listing = mgr.list_sessions()
    assert len(listing) == 2

    sids = {s["session_id"] for s in listing}
    assert "s1" in sids
    assert "s2" in sids

    return True


# ===================================================================
#  Run All Tests
# ===================================================================

if __name__ == "__main__":
    print("~" * 60)
    print("VOICE LAYER TEST SUITE -- AI Interviewer v4.0")
    print("~" * 60)

    tests = [
        test_session_creation,
        test_session_expiry,
        test_session_close,
        test_vad_speech_end,
        test_transcript_buffer,
        test_barge_in,
        test_context_guard,
        test_streaming_response,
        test_compact_eval,
        test_combined_interruption_check,
        test_session_listing,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = test()
            if result:
                print(f"[PASS] {test.__name__}")
                passed += 1
            else:
                print(f"[FAIL] {test.__name__} returned False")
                failed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__} ERROR: {e}")
            failed += 1

    print()
    print("~" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("~" * 60)
