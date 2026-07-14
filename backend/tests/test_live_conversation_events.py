"""Unit tests for live conversation event projection (UI outbound only)."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from pipecat_integration.conversation.events import (
    SCHEMA_VERSION,
    WIRE_TYPE,
    make_message_event,
    make_phase_event,
)
from pipecat_integration.conversation.publisher import ConversationEventPublisher
from pipecat_integration.interview_processor import (
    FrameDirection,
    InterviewProcessor,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from voice.voice_turn_policy import VoiceTurnPolicy, DEFAULT_FILLER_WORDS


class CaptureProcessor(InterviewProcessor):
    def __init__(self, adapter, session_id):
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
            barge_in_min_bot_speak_seconds=0,
            final_transcript_debounce_seconds=0,
            filler_words=DEFAULT_FILLER_WORDS,
        )
        super().__init__(adapter, session_id, policy=policy)
        self.pushed_frames = []
        self.reset_for_new_session()

    async def push_frame(self, frame, direction):
        self.pushed_frames.append((frame, direction))


def _conversation_payloads(processor: CaptureProcessor) -> list[dict]:
    out = []
    for frame, _ in processor.pushed_frames:
        msg = getattr(frame, "message", None)
        if isinstance(msg, dict) and msg.get("type") == WIRE_TYPE:
            out.append(msg)
    return out


async def _flush(processor: CaptureProcessor) -> None:
    if processor._debounce_task and not processor._debounce_task.done():
        await processor._debounce_task
    if processor._interim_finalize_task and not processor._interim_finalize_task.done():
        await processor._interim_finalize_task


def test_message_event_schema():
    event = make_message_event(
        role="user",
        text="Hello world",
        session_id="s1",
        turn_id="t1",
    )
    assert event["type"] == WIRE_TYPE
    assert event["schema_version"] == SCHEMA_VERSION
    assert event["kind"] == "message"
    assert event["role"] == "user"
    assert event["text"] == "Hello world"
    assert event["status"] == "final"
    assert event["session_id"] == "s1"
    assert event["turn_id"] == "t1"
    assert event["message_id"]
    assert event["event_id"]
    assert event["ts"]


def test_phase_event_schema():
    event = make_phase_event(phase="thinking", session_id="s1")
    assert event["kind"] == "phase"
    assert event["phase"] == "thinking"


def test_publisher_binds_session_id():
    pub = ConversationEventPublisher(lambda: "sess-42")
    event = pub.message(role="assistant", text="Question?")
    assert event["session_id"] == "sess-42"
    frame = pub.frame_for(event)
    assert getattr(frame, "message", None) == event


async def test_processor_emits_user_and_bot_conversation_events():
    mock_adapter = MagicMock()
    mock_adapter.process_user_text.return_value = {
        "session_id": "test-session",
        "ai_response_text": "Tell me more about that project.",
        "current_state": "technical",
        "is_complete": False,
        "error": None,
    }
    processor = CaptureProcessor(mock_adapter, "test-session")
    frame = TranscriptionFrame(
        text="I built an ASR pipeline with Whisper.",
        user_id="u",
        timestamp="0",
        finalized=True,
    )
    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)
    await _flush(processor)

    events = _conversation_payloads(processor)
    user_msgs = [e for e in events if e.get("kind") == "message" and e.get("role") == "user"]
    bot_msgs = [
        e for e in events if e.get("kind") == "message" and e.get("role") == "assistant"
    ]
    phases = [e for e in events if e.get("kind") == "phase"]

    assert len(user_msgs) == 1
    assert user_msgs[0]["text"] == "I built an ASR pipeline with Whisper."
    assert len(bot_msgs) == 1
    assert bot_msgs[0]["text"] == "Tell me more about that project."
    assert user_msgs[0]["turn_id"] and user_msgs[0]["turn_id"] == bot_msgs[0]["turn_id"]
    assert any(p.get("phase") == "thinking" for p in phases)

    tts = [f for f, _ in processor.pushed_frames if isinstance(f, TTSSpeakFrame)]
    assert len(tts) == 1
    assert tts[0].text == "Tell me more about that project."


def main():
    test_message_event_schema()
    test_phase_event_schema()
    test_publisher_binds_session_id()
    asyncio.run(test_processor_emits_user_and_bot_conversation_events())
    print("[PASS] test_live_conversation_events")


if __name__ == "__main__":
    main()
