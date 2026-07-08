"""Phase 6 — false barge-in protection (server grace after bot starts)."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from pipecat_integration.interview_processor import (
    BotStartedSpeakingFrame,
    FrameDirection,
    InterviewProcessor,
    VADUserStartedSpeakingFrame,
)
from voice.voice_turn_policy import DEFAULT_FILLER_WORDS, VoiceTurnPolicy


class CaptureProcessor(InterviewProcessor):
    def __init__(self, barge_grace: float = 1.0):
        policy = VoiceTurnPolicy(
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
            barge_in_min_bot_speak_seconds=barge_grace,
            filler_words=DEFAULT_FILLER_WORDS,
        )
        super().__init__(MagicMock(), "barge-test", policy=policy)
        self.pushed_frames = []
        self.broadcast_interruption = AsyncMock()
        self.first_real_user_turn_seen = True
        self.startup_audio_ignore_until = 0

    async def push_frame(self, frame, direction):
        self.pushed_frames.append((frame, direction))


async def test_early_vad_does_not_interrupt():
    proc = CaptureProcessor(barge_grace=1.0)
    await proc.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert proc.bot_is_speaking
    await proc.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    proc.broadcast_interruption.assert_not_awaited()
    assert proc.bot_is_speaking


async def test_late_vad_does_interrupt():
    proc = CaptureProcessor(barge_grace=0.2)
    await proc.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    proc._bot_speech_started_at = time.time() - 0.5
    await proc.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    proc.broadcast_interruption.assert_awaited_once()
    assert not proc.bot_is_speaking


def test_client_config_defaults_raised():
    import re

    cfg_path = os.path.join(
        backend_dir,
        "pipecat_integration",
        "manual_client",
        "config.js",
    )
    text = open(cfg_path, encoding="utf-8").read()
    assert 'barge_rms") || "0.09"' in text or re.search(r'barge_rms.*"0\.09"', text)
    assert 'barge_frames") || "6"' in text
    assert 'barge_ignore_ms") || "1000"' in text


if __name__ == "__main__":
    asyncio.run(test_early_vad_does_not_interrupt())
    asyncio.run(test_late_vad_does_interrupt())
    test_client_config_defaults_raised()
    print("[PASS] test_phase6_barge_in")
