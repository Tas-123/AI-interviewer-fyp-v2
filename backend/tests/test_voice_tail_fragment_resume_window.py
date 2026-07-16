"""
Voice tail fragment resume window — July 15/16 fragmentation regression tests.

Simulates: long answer submitted, then short STT tail arrives within resume window.
Expectation: tail is suppressed/merged so adapter.process_user_text is not called again.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from pipecat_integration.interview_processor import (
    FrameDirection,
    InterviewProcessor,
    TranscriptionFrame,
)
from voice.voice_turn_policy import DEFAULT_FILLER_WORDS, VoiceTurnPolicy


def _policy(**overrides) -> VoiceTurnPolicy:
    base = dict(
        transcript_debounce_seconds=3.0,
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
        final_transcript_debounce_seconds=0.05,
        filler_words=DEFAULT_FILLER_WORDS,
        turn_resume_window_seconds=0.75,
        turn_tail_max_words=6,
        turn_tail_min_words_for_suspicion=10,
    )
    base.update(overrides)
    return VoiceTurnPolicy(**base)


class CaptureProcessor(InterviewProcessor):
    def __init__(self, adapter):
        super().__init__(adapter, "tail-test", policy=_policy())
        self.first_real_user_turn_seen = True
        self.startup_audio_ignore_until = 0

    async def push_frame(self, frame, direction):
        pass

    async def _emit_conversation(self, message, direction):
        pass

    async def _emit_phase(self, phase, direction):
        pass


LONG_ANSWER = (
    "I trained a random forest classifier on tabular data and evaluated accuracy, "
    "precision, recall, and F1 on a held-out test set with cross validation."
)


def test_post_submit_redundant_tail_discarded():
    """July 16 pattern: tail repeats phrase already in submitted answer."""

    async def _run():
        adapter = MagicMock()
        adapter.process_user_text = MagicMock(
            return_value={"ai_response_text": "Thanks.", "is_complete": False}
        )
        proc = CaptureProcessor(adapter)
        proc._open_resume_window(LONG_ANSWER + " And the model generalized well.")

        tail = "the model generalized well."
        proc.latest_user_transcript = tail
        result = await proc._prepare_transcript_for_turn()
        assert result is None
        assert adapter.process_user_text.call_count == 0

    asyncio.run(_run())


def test_substantial_submit_then_tail_only_one_adapter_call():
    """After a long answer is submitted, a short tail must not create a second turn."""

    async def _run():
        adapter = MagicMock()
        adapter.process_user_text = MagicMock(
            return_value={"ai_response_text": "Thanks.", "is_complete": False}
        )
        proc = CaptureProcessor(adapter)

        await proc._submit_turn(LONG_ANSWER, FrameDirection.DOWNSTREAM)
        assert adapter.process_user_text.call_count == 1
        assert proc._in_resume_window()

        proc.latest_user_transcript = "the model generalized well."
        tail_result = await proc._prepare_transcript_for_turn()
        assert tail_result is None
        assert adapter.process_user_text.call_count == 1

    asyncio.run(_run())


def test_substantial_answer_uses_extended_debounce():
    """Long buffered answers wait through the resume window before finalizing."""
    proc = CaptureProcessor(MagicMock())
    proc.latest_user_transcript = LONG_ANSWER
    delay = proc._compute_turn_debounce_delay()
    assert delay >= proc.policy.turn_resume_window_seconds


def test_final_stt_tail_merged_before_submit():
    """Tail arriving before debounce fires stays on one merged turn (July 15 pattern)."""

    async def _run():
        adapter = MagicMock()
        adapter.process_user_text = MagicMock(
            return_value={"ai_response_text": "Thanks.", "is_complete": False}
        )
        proc = CaptureProcessor(adapter)

        await proc.process_frame(
            TranscriptionFrame(LONG_ANSWER),
            FrameDirection.DOWNSTREAM,
        )
        await asyncio.sleep(0.08)

        await proc.process_frame(
            TranscriptionFrame("database for that."),
            FrameDirection.DOWNSTREAM,
        )
        await asyncio.sleep(0.9)

        if proc._debounce_task and not proc._debounce_task.done():
            await proc._debounce_task

        assert adapter.process_user_text.call_count == 1
        submitted = adapter.process_user_text.call_args[0][1]
        assert "database for that" in submitted.lower()

    asyncio.run(_run())


def test_resume_window_expires_allows_new_turn():
    """After resume window ends, a genuinely new short answer may be submitted."""

    async def _run():
        adapter = MagicMock()
        adapter.process_user_text = MagicMock(
            return_value={"ai_response_text": "Thanks.", "is_complete": False}
        )
        proc = CaptureProcessor(adapter)
        proc._open_resume_window(LONG_ANSWER)
        proc._resume_window_until = time.time() - 0.01

        proc.latest_user_transcript = "skip this question please"
        result = await proc._prepare_transcript_for_turn()
        assert result is not None
        assert "skip" in result.lower()

    asyncio.run(_run())


if __name__ == "__main__":
    test_post_submit_redundant_tail_discarded()
    test_substantial_submit_then_tail_only_one_adapter_call()
    test_substantial_answer_uses_extended_debounce()
    test_final_stt_tail_merged_before_submit()
    test_resume_window_expires_allows_new_turn()
    print("[PASS] test_voice_tail_fragment_resume_window")
