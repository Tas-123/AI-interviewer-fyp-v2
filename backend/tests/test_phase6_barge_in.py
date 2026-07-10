"""Barge-in rebalance — interruption should work after Phase 6 tuning."""

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
    def __init__(self, barge_grace: float = 0.25):
        policy = VoiceTurnPolicy(
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
            barge_in_min_bot_speak_seconds=barge_grace,
            final_transcript_debounce_seconds=0.35,
            filler_words=DEFAULT_FILLER_WORDS,
        )
        super().__init__(MagicMock(), "barge-test", policy=policy)
        self.pushed_frames = []
        self.broadcast_interruption = AsyncMock()
        self.first_real_user_turn_seen = True
        self.startup_audio_ignore_until = 0

    async def push_frame(self, frame, direction):
        self.pushed_frames.append((frame, direction))


async def test_vad_interrupts_after_grace():
    proc = CaptureProcessor(barge_grace=0.25)
    await proc.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    proc._bot_speech_started_at = time.time() - 0.5
    await proc.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    proc.broadcast_interruption.assert_awaited_once()
    assert not proc.bot_is_speaking


async def test_stt_words_trigger_early_barge_in():
    proc = CaptureProcessor(barge_grace=0.25)
    await proc.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert proc.bot_is_speaking
    interrupted = await proc._maybe_interrupt_bot(
        "I think the answer is about weather features"
    )
    assert interrupted
    proc.broadcast_interruption.assert_awaited_once()


def test_client_config_balanced_defaults():
    cfg_path = os.path.join(
        backend_dir,
        "pipecat_integration",
        "manual_client",
        "config.js",
    )
    text = open(cfg_path, encoding="utf-8").read()
    assert '"0.055"' in text
    assert '"4"' in text
    assert '"500"' in text


if __name__ == "__main__":
    asyncio.run(test_vad_interrupts_after_grace())
    asyncio.run(test_stt_words_trigger_early_barge_in())
    test_client_config_balanced_defaults()
    print("[PASS] test_phase6_barge_in")
