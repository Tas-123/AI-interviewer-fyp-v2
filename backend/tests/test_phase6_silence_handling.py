"""Phase 6 — candidate silence nudge / rephrase watch."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from pipecat_integration.interview_processor import (
    BotStoppedSpeakingFrame,
    FrameDirection,
    InterviewProcessor,
    TTSSpeakFrame,
    VADUserStartedSpeakingFrame,
)
from voice.voice_turn_policy import (
    DEFAULT_FILLER_WORDS,
    SILENCE_NUDGE_TEXT,
    SILENCE_REPHRASE_TEXT,
    VoiceTurnPolicy,
)


class CaptureProcessor(InterviewProcessor):
    def __init__(self):
        policy = VoiceTurnPolicy(
            transcript_debounce_seconds=0,
            short_answer_grace_seconds=0,
            short_answer_word_threshold=6,
            startup_audio_gate_seconds=0,
            startup_refresh_seconds=0,
            bot_echo_cooldown_seconds=0,
            bot_stop_echo_cooldown_seconds=0,
            closing_delay_seconds=0,
            candidate_silence_nudge_seconds=0.05,
            candidate_silence_rephrase_seconds=0.10,
            barge_in_min_bot_speak_seconds=1.0,
            filler_words=DEFAULT_FILLER_WORDS,
        )
        super().__init__(MagicMock(), "silence-test", policy=policy)
        self.pushed_frames = []
        self.first_real_user_turn_seen = True
        self.startup_audio_ignore_until = 0

    async def push_frame(self, frame, direction):
        self.pushed_frames.append((frame, direction))


async def test_silence_nudge_and_rephrase():
    proc = CaptureProcessor()
    await proc.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert proc._silence_watch_task is not None
    # Settle delay (~0.85s) + nudge (0.05s)
    await asyncio.sleep(1.05)
    texts = [f.text for f, _ in proc.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert SILENCE_NUDGE_TEXT in texts
    # Remaining to rephrase (0.05s) + margin
    await asyncio.sleep(0.20)
    texts = [f.text for f, _ in proc.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert SILENCE_REPHRASE_TEXT in texts


async def test_silence_cancelled_when_user_speaks():
    proc = CaptureProcessor()
    await proc.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await proc.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await asyncio.sleep(1.2)
    texts = [f.text for f, _ in proc.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert SILENCE_NUDGE_TEXT not in texts
    assert SILENCE_REPHRASE_TEXT not in texts


async def test_silence_not_restarted_by_nudge_tts_bot_stopped():
    """Nudge TTS BotStopped must not spawn a second infinite watch loop."""
    proc = CaptureProcessor()
    await proc.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    # Catch the window after nudge, before rephrase (settle 0.85 + nudge 0.05)
    await asyncio.sleep(0.95)
    assert proc._silence_stage == "nudged"
    first_task = proc._silence_watch_task
    await proc.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert proc._silence_watch_task is first_task
    await asyncio.sleep(0.25)
    texts = [f.text for f, _ in proc.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert texts.count(SILENCE_NUDGE_TEXT) == 1
    assert texts.count(SILENCE_REPHRASE_TEXT) == 1


if __name__ == "__main__":
    asyncio.run(test_silence_nudge_and_rephrase())
    asyncio.run(test_silence_cancelled_when_user_speaks())
    asyncio.run(test_silence_not_restarted_by_nudge_tts_bot_stopped())
    print("[PASS] test_silence_handling")
