"""
InterviewProcessor — Custom Pipecat FrameProcessor that bridges the Pipecat STT/TTS pipeline
with the existing InterviewDialogueAdapter.

Phase 5: config-driven VoiceTurnPolicy, unified _submit_turn(), async Groq via to_thread.
"""

from __future__ import annotations

import asyncio
import logging
import time

from core.config import settings
from core.interviewer_policy import INTERVIEW_CLOSING_SPOKEN, LLM_ERROR_TTS_FALLBACK
from dialogue.output_sanitizer import strip_followup_prefix
from voice.voice_turn_policy import VoiceTurnPolicy

logger = logging.getLogger("InterviewProcessor")


def sanitize_tts_text(text: str) -> str:
    """
    Strip internal labels and substitute a spoken fallback when LLM generation failed.
    """
    if not text:
        return text
    text = strip_followup_prefix(text)
    if text.startswith("[Error") or "Error generating question" in text:
        logger.warning("LLM error detected in TTS path: %r — using fallback greeting.", text)
        return LLM_ERROR_TTS_FALLBACK
    return text


try:
    from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
    from pipecat.frames.frames import (
        Frame,
        TextFrame,
        TranscriptionFrame,
        EndTaskFrame,
        TTSSpeakFrame,
        InterimTranscriptionFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        BotSpeakingFrame,
    )
except ImportError:
    logger.warning(
        "Pipecat-ai not installed in this environment. Using mock definitions for dry-run/testing."
    )

    class FrameProcessor:
        def __init__(self):
            pass

        async def process_frame(self, frame, direction):
            pass

        async def push_frame(self, frame, direction):
            pass

    class FrameDirection:
        UPSTREAM = 1
        DOWNSTREAM = 2

    class Frame:
        pass

    class TextFrame(Frame):
        def __init__(self, text: str):
            self.text = text

    class TTSSpeakFrame(Frame):
        def __init__(self, text: str, append_to_context: bool = True):
            self.text = text
            self.append_to_context = append_to_context

    class TranscriptionFrame(TextFrame):
        def __init__(
            self,
            text: str,
            user_id: str = "test-user",
            timestamp: str = "0",
            language=None,
            result=None,
            finalized: bool = True,
        ):
            super().__init__(text)
            self.user_id = user_id
            self.timestamp = timestamp
            self.finalized = finalized

    class EndTaskFrame(Frame):
        pass

    class BotStartedSpeakingFrame(Frame):
        pass

    class BotStoppedSpeakingFrame(Frame):
        pass

    class BotSpeakingFrame(Frame):
        pass

    class InterimTranscriptionFrame(Frame):
        def __init__(self, text: str):
            self.text = text

    class VADUserStartedSpeakingFrame(Frame):
        pass

    class VADUserStoppedSpeakingFrame(Frame):
        pass


class InterviewProcessor(FrameProcessor):
    """
    FrameProcessor that intercepts user speech transcripts (TranscriptionFrame),
    queries the dialogue adapter, and pushes the AI's response text (TextFrame)
    downstream to the TTS engine.
    """

    def __init__(self, adapter, session_id: str, policy: VoiceTurnPolicy | None = None):
        super().__init__()
        self.adapter = adapter
        self.session_id = session_id
        self.policy = policy or VoiceTurnPolicy.from_settings(settings)
        self.log_frames = settings.processor_log_frames

        self.last_processed_transcript = ""
        self.latest_user_transcript = ""
        self.utterance_parts: list[str] = []

        self.bot_is_speaking = False
        self.ignore_user_audio_until = 0.0
        self.vad_enabled = False
        self._debounce_task: asyncio.Task | None = None

        self.last_barge_in_at = 0.0
        self.barge_in_active = False

        self.startup_audio_ignore_until = time.time() + self.policy.startup_audio_gate_seconds
        self.first_real_user_turn_seen = False

    def _merge_transcript_part(self, user_text: str) -> None:
        """Accumulate partial STT chunks into the longest useful utterance."""
        user_text = (user_text or "").strip()
        if not user_text:
            return

        if not self.utterance_parts:
            self.utterance_parts.append(user_text)
            self.latest_user_transcript = user_text
            return

        current = " ".join(self.utterance_parts).strip()

        if current and current.lower() in user_text.lower():
            self.utterance_parts = [user_text]
            self.latest_user_transcript = user_text
            return

        if user_text.lower() in current.lower():
            self.latest_user_transcript = current
            return

        self.utterance_parts.append(user_text)
        self.latest_user_transcript = " ".join(self.utterance_parts).strip()

    def _clean_transcript_for_evaluation(self, text: str) -> str:
        from dialogue.transcript_utils import clean_live_transcript

        return clean_live_transcript(text)

    def _clear_transcript_buffer(self) -> None:
        self.latest_user_transcript = ""
        self.utterance_parts = []

    def _should_ignore_startup(self, user_text: str) -> bool:
        if self.first_real_user_turn_seen:
            return False
        if time.time() >= self.startup_audio_ignore_until:
            return False
        logger.info("Ignoring startup transcript before interview is ready: %r", user_text)
        self._clear_transcript_buffer()
        return True

    def _should_ignore_echo(self, user_text: str) -> bool:
        if time.time() >= self.ignore_user_audio_until:
            return False
        logger.info("Ignoring transcript during bot echo cooldown: %r", user_text)
        self._clear_transcript_buffer()
        return True

    async def _apply_short_answer_grace(self, user_text: str) -> str:
        if not self.policy.is_short_answer(user_text):
            return user_text

        word_count = len(user_text.split())
        logger.info(
            "Short transcript (%d words), waiting grace period: %r",
            word_count,
            user_text,
        )
        await asyncio.sleep(self.policy.short_answer_grace_seconds)
        updated = getattr(self, "latest_user_transcript", "").strip()
        if updated and updated != user_text:
            cleaned = self._clean_transcript_for_evaluation(updated)
            if cleaned:
                logger.info("Extended transcript after grace: %r", cleaned)
                return cleaned
        return user_text

    async def _prepare_transcript_for_turn(self) -> str | None:
        """Shared gating, cleaning, and grace logic before submitting a turn."""
        user_text = getattr(self, "latest_user_transcript", "").strip()
        if not user_text:
            logger.debug("No buffered transcript to process.")
            return None

        if self._should_ignore_startup(user_text):
            return None
        if self._should_ignore_echo(user_text):
            return None
        if self.policy.is_filler(user_text):
            logger.info("Ignoring filler transcript: %r", user_text)
            return None

        if self.barge_in_active:
            logger.info("Processing transcript captured after barge-in: %r", user_text)

        cleaned = self._clean_transcript_for_evaluation(user_text)
        if cleaned != user_text:
            logger.info("Cleaned transcript for evaluation: %r", cleaned)
            user_text = cleaned

        user_text = await self._apply_short_answer_grace(user_text)

        self._clear_transcript_buffer()

        if self.policy.is_filler(user_text):
            logger.info("Ignoring filler transcript after grace: %r", user_text)
            return None
        if user_text == self.last_processed_transcript:
            logger.info("Duplicate transcript skipped: %r", user_text)
            return None

        return user_text

    async def _submit_turn(self, user_text: str, direction: FrameDirection) -> None:
        """Process one complete transcript through the adapter and push TTS response."""
        self.last_processed_transcript = user_text
        self.first_real_user_turn_seen = True
        was_barge_in = self.barge_in_active

        logger.info("Processing user transcript: %r", user_text)
        if was_barge_in:
            logger.info("Transcript from barge-in turn — dialogue policy will classify.")

        try:
            response = await asyncio.to_thread(
                self.adapter.process_user_text,
                self.session_id,
                user_text,
            )

            if was_barge_in:
                logger.debug("Resetting barge-in state after transcript processing.")
                self.barge_in_active = False

            if response.get("error"):
                logger.error("Adapter error: %s", response["error"])
                await self.push_frame(
                    TTSSpeakFrame(
                        "I'm sorry, I had trouble processing that response. Could you please repeat?"
                    ),
                    direction,
                )
                return

            ai_text = sanitize_tts_text(response.get("ai_response_text", ""))
            is_complete = response.get("is_complete", False)

            if ai_text:
                await self.push_frame(TTSSpeakFrame(ai_text), direction)

            if is_complete:
                logger.info(
                    "Interview %s complete — spoken closing then EndTaskFrame.",
                    self.session_id,
                )
                await self.push_frame(TTSSpeakFrame(INTERVIEW_CLOSING_SPOKEN), direction)
                await asyncio.sleep(self.policy.closing_delay_seconds)
                await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

        except Exception:
            logger.exception("Failed to process turn in InterviewProcessor")
            await self.push_frame(
                TTSSpeakFrame("I'm sorry, I encountered an internal error. Let's try again."),
                direction,
            )

    async def _process_buffered_transcript_after_delay(self) -> None:
        try:
            await asyncio.sleep(self.policy.transcript_debounce_seconds)

            if self.bot_is_speaking:
                logger.debug("Bot still speaking; processing saved transcript after debounce.")

            user_text = await self._prepare_transcript_for_turn()
            if not user_text:
                return

            await self._submit_turn(user_text, FrameDirection.DOWNSTREAM)

        except asyncio.CancelledError:
            logger.debug("Debounce task cancelled — user started speaking again.")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if self.log_frames:
            logger.debug(
                "process_frame: %s (direction=%s)",
                type(frame).__name__,
                direction,
            )

        if isinstance(frame, (BotStartedSpeakingFrame, BotSpeakingFrame)):
            logger.debug("Bot started speaking — mic echo cooldown active")
            self.bot_is_speaking = True
            self.ignore_user_audio_until = time.time() + self.policy.bot_echo_cooldown_seconds

            if not self.first_real_user_turn_seen:
                self.startup_audio_ignore_until = max(
                    self.startup_audio_ignore_until,
                    time.time() + self.policy.startup_refresh_seconds,
                )
                logger.debug(
                    "Startup audio gate refreshed until %.1f",
                    self.startup_audio_ignore_until,
                )

            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            logger.debug("Bot stopped speaking — short mic echo cooldown")
            self.bot_is_speaking = False
            self.ignore_user_audio_until = (
                time.time() + self.policy.bot_stop_echo_cooldown_seconds
            )
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            logger.debug("VAD: user started speaking")
            self.vad_enabled = True
            if self.bot_is_speaking:
                logger.info("User interrupted bot — broadcasting interruption")
                self.last_barge_in_at = time.time()
                self.barge_in_active = True
                await self.broadcast_interruption()
                self.bot_is_speaking = False

            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()
                logger.debug("Cancelled debounce task — user speaking again")

            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            logger.debug("VAD: user stopped speaking")
            self.vad_enabled = True

            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()

            self._debounce_task = asyncio.create_task(
                self._process_buffered_transcript_after_delay()
            )
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterimTranscriptionFrame):
            interim_text = (getattr(frame, "text", "") or "").strip()
            if interim_text:
                self._merge_transcript_part(interim_text)
                logger.debug("Buffered interim transcript: %r", interim_text)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            user_text = (frame.text or "").strip()

            if getattr(frame, "finalized", True) is False:
                if user_text:
                    self._merge_transcript_part(user_text)
                    logger.debug("Stored non-final transcription: %r", user_text)
                await self.push_frame(frame, direction)
                return

            if self.bot_is_speaking:
                if user_text:
                    self._merge_transcript_part(user_text)
                    logger.debug("Stored transcript while bot speaking: %r", user_text)
                return

            if self.vad_enabled:
                if not user_text:
                    logger.warning("Empty transcript in VAD mode — ignoring.")
                    return
                self._merge_transcript_part(user_text)
                logger.debug("Buffered final transcript (VAD): %r", user_text)
                return

            # Non-VAD path (unit tests / providers without VAD)
            if not user_text:
                logger.warning("Empty transcript (non-VAD) — requesting clarification.")
                await self.push_frame(
                    TTSSpeakFrame("I didn't catch that. Could you please repeat or elaborate?"),
                    direction,
                )
                return

            if user_text == self.last_processed_transcript:
                logger.info("Duplicate transcript skipped (non-VAD): %r", user_text)
                return

            cleaned = self._clean_transcript_for_evaluation(user_text)
            if cleaned:
                user_text = cleaned

            await self._submit_turn(user_text, direction)
            return

        await self.push_frame(frame, direction)
