"""
Voice turn-taking fixes — interim fallback, echo/barge-in, junk turns, early guards.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.guards.intent_guard import IntentGuard
from dialogue.guards.types import GuardContext
from pipecat_integration.interview_processor import InterviewProcessor
from voice.voice_turn_policy import DEFAULT_FILLER_WORDS, VoiceTurnPolicy


def _policy(**overrides) -> VoiceTurnPolicy:
    base = dict(
        transcript_debounce_seconds=3.0,
        short_answer_grace_seconds=0,
        short_answer_word_threshold=6,
        startup_audio_gate_seconds=0,
        startup_refresh_seconds=0,
        bot_echo_cooldown_seconds=1.2,
        bot_stop_echo_cooldown_seconds=0.8,
        closing_delay_seconds=0,
        candidate_silence_nudge_seconds=0,
        candidate_silence_rephrase_seconds=0,
        barge_in_min_bot_speak_seconds=0.25,
        final_transcript_debounce_seconds=0.35,
        filler_words=DEFAULT_FILLER_WORDS,
    )
    base.update(overrides)
    return VoiceTurnPolicy(**base)


class CaptureProcessor(InterviewProcessor):
    def __init__(self):
        super().__init__(MagicMock(), "turn-test", policy=_policy())
        self.broadcast_interruption = AsyncMock()
        self.first_real_user_turn_seen = True
        self.startup_audio_ignore_until = 0
        self._interim_silence_seconds = 0.01

    async def push_frame(self, frame, direction):
        pass


def test_interim_fallback_skips_short_partial_without_final():
    async def _run():
        proc = CaptureProcessor()
        proc._user_vad_speaking = False
        proc._saw_final_stt_for_utterance = False
        proc.latest_user_transcript = "Yeah. So"
        scheduled = []
        proc._schedule_turn_debounce = lambda delay=None: scheduled.append(delay)
        await proc._finalize_buffered_interim_after_silence()
        assert scheduled == []

    asyncio.run(_run())


def test_interim_fallback_allows_substantial_quiet_utterance():
    async def _run():
        proc = CaptureProcessor()
        proc._user_vad_speaking = False
        proc._saw_final_stt_for_utterance = False
        proc.latest_user_transcript = (
            "My name is Gary and I have three years of experience working on OCR systems"
        )
        scheduled = []
        proc._schedule_turn_debounce = lambda delay=None: scheduled.append(delay)
        await proc._finalize_buffered_interim_after_silence()
        assert len(scheduled) == 1

    asyncio.run(_run())


def test_interim_fallback_skips_when_vad_still_speaking():
    async def _run():
        proc = CaptureProcessor()
        proc._user_vad_speaking = True
        proc._saw_final_stt_for_utterance = False
        proc.latest_user_transcript = (
            "My name is Gary and I have three years of experience working on OCR systems"
        )
        scheduled = []
        proc._schedule_turn_debounce = lambda delay=None: scheduled.append(delay)
        await proc._finalize_buffered_interim_after_silence()
        assert scheduled == []

    asyncio.run(_run())


def test_echo_ignored_during_barge_in_mic_allow():
    proc = CaptureProcessor()
    proc.ignore_user_audio_until = time.time() + 5.0
    proc.barge_in_active = True
    proc._barge_in_mic_allow_until = time.time() + 2.5
    proc.latest_user_transcript = "I have three years of experience"
    assert proc._should_ignore_echo(proc.latest_user_transcript) is False
    assert proc.latest_user_transcript == "I have three years of experience"


def test_echo_clears_outside_barge_in_window():
    proc = CaptureProcessor()
    proc.ignore_user_audio_until = time.time() + 5.0
    proc.barge_in_active = False
    proc._barge_in_mic_allow_until = 0.0
    proc.latest_user_transcript = "echoed bot text"
    assert proc._should_ignore_echo(proc.latest_user_transcript) is True
    assert proc.latest_user_transcript == ""


def test_junk_post_barge_in_transcript_discarded():
    async def _run():
        proc = CaptureProcessor()
        proc.barge_in_active = True
        proc._barge_in_mic_allow_until = time.time() + 2.5
        proc.latest_user_transcript = "So Hello?"
        result = await proc._prepare_transcript_for_turn()
        assert result is None

    asyncio.run(_run())


def test_check_in_helper():
    assert InterviewProcessor._is_check_in_or_junk("hello?") is True
    assert InterviewProcessor._is_check_in_or_junk("hear me?") is True
    assert (
        InterviewProcessor._is_check_in_or_junk(
            "I built an OCR pipeline with PaddleOCR and FastAPI"
        )
        is False
    )


def test_early_audio_issue_softened():
    guard = IntentGuard()
    ctx = GuardContext(
        transcript="Hello? Can you hear me?",
        last_question="Please introduce yourself.",
        interview_context=SimpleNamespace(turn_count=1),
    )
    result = guard.check(ctx)
    assert result.triggered is False


def test_later_audio_issue_still_triggers():
    guard = IntentGuard()
    ctx = GuardContext(
        transcript="Hello? Can you hear me?",
        last_question="How would you detect overfitting?",
        interview_context=SimpleNamespace(turn_count=5),
    )
    result = guard.check(ctx)
    assert result.triggered is True
    assert result.decision_type == "AUDIO_ISSUE"


if __name__ == "__main__":
    test_interim_fallback_skips_short_partial_without_final()
    test_interim_fallback_allows_substantial_quiet_utterance()
    test_interim_fallback_skips_when_vad_still_speaking()
    test_echo_ignored_during_barge_in_mic_allow()
    test_echo_clears_outside_barge_in_window()
    test_junk_post_barge_in_transcript_discarded()
    test_check_in_helper()
    test_early_audio_issue_softened()
    test_later_audio_issue_still_triggers()
    print("[PASS] test_voice_turn_taking_fixes")
