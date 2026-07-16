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
from pipecat_integration.conversation.publisher import ConversationEventPublisher
from voice.voice_turn_policy import (
    SILENCE_NUDGE_TEXT,
    SILENCE_REPHRASE_TEXT,
    VoiceTurnPolicy,
)

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
        self.conversation = ConversationEventPublisher(lambda: self.session_id)

        self.last_processed_transcript = ""
        self.latest_user_transcript = ""
        self.utterance_parts: list[str] = []

        self.bot_is_speaking = False
        self.ignore_user_audio_until = 0.0
        self.vad_enabled = False
        self._debounce_task: asyncio.Task | None = None

        self.last_barge_in_at = 0.0
        self.barge_in_active = False
        self._bot_speech_started_at = 0.0
        # After barge-in, allow mic transcripts despite echo cooldown (seconds).
        self._barge_in_mic_allow_until = 0.0
        self._barge_in_mic_allow_seconds = 2.5
        self._barge_in_echo_cooldown_seconds = 0.25
        # Suppress re-speaking the interrupted question immediately after barge-in.
        self._barge_in_tts_suppress_until = 0.0
        self._last_spoken_assistant_text = ""
        self._barge_in_settle_seconds = 0.45

        self.startup_audio_ignore_until = time.time() + self.policy.startup_audio_gate_seconds
        self.first_real_user_turn_seen = False
        self._interim_silence_seconds = 1.4
        self._interim_min_words = 8
        self._user_vad_speaking = False
        self._saw_final_stt_for_utterance = False
        self._interim_finalize_task: asyncio.Task | None = None
        self._silence_watch_task: asyncio.Task | None = None
        self._silence_nudge_sent = False
        self._awaiting_candidate_answer = False
        # None | "watching" | "nudged" | "done" — prevents nudge TTS from restarting the watch
        self._silence_stage: str | None = None

        # Resume window: absorb short STT tails shortly after a substantial submit.
        self._resume_window_until = 0.0
        self._last_submitted_transcript = ""
        self._last_submitted_word_count = 0

    async def request_client_interrupt(self, reason: str = "client_interrupt") -> None:
        """Stop bot TTS promptly when the browser client detects user barge-in."""
        logger.info("Client interrupt received — broadcasting interruption (%s)", reason)
        self.last_barge_in_at = time.time()
        self.barge_in_active = True
        self._barge_in_mic_allow_until = time.time() + self._barge_in_mic_allow_seconds
        self._barge_in_tts_suppress_until = time.time() + self._barge_in_settle_seconds + 2.0
        self._note_candidate_activity()
        await self.broadcast_interruption()

    def reset_for_new_session(self) -> None:
        """Reset per-session processor state when a new WebSocket client connects."""
        self.last_processed_transcript = ""
        self.latest_user_transcript = ""
        self.utterance_parts = []
        self.bot_is_speaking = False
        self.ignore_user_audio_until = 0.0
        self.vad_enabled = False
        self.last_barge_in_at = 0.0
        self.barge_in_active = False
        self._bot_speech_started_at = 0.0
        self._barge_in_mic_allow_until = 0.0
        self._barge_in_tts_suppress_until = 0.0
        self._last_spoken_assistant_text = ""
        self._user_vad_speaking = False
        self._saw_final_stt_for_utterance = False
        self.startup_audio_ignore_until = time.time() + self.policy.startup_audio_gate_seconds
        self.first_real_user_turn_seen = False
        self._silence_nudge_sent = False
        self._awaiting_candidate_answer = False
        self._silence_stage = None
        self._resume_window_until = 0.0
        self._last_submitted_transcript = ""
        self._last_submitted_word_count = 0
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None
        if self._interim_finalize_task and not self._interim_finalize_task.done():
            self._interim_finalize_task.cancel()
        self._interim_finalize_task = None
        self._cancel_silence_watch()

    def _cancel_silence_watch(self) -> None:
        if self._silence_watch_task and not self._silence_watch_task.done():
            self._silence_watch_task.cancel()
        self._silence_watch_task = None

    def _schedule_silence_watch(self) -> None:
        """After bot finishes speaking, nudge / rephrase if the candidate stays silent."""
        if self.policy.candidate_silence_nudge_seconds <= 0:
            return
        # Do not restart while a silence cycle is already in progress (nudge/rephrase TTS)
        if self._silence_stage in ("watching", "nudged", "done"):
            return
        self._cancel_silence_watch()
        self._silence_nudge_sent = False
        self._silence_watch_task = asyncio.create_task(self._candidate_silence_watch())

    async def _candidate_silence_watch(self) -> None:
        """Soft nudge, then a rephrase prompt, if no speech/STT arrives.

        Starts with a short settle delay so chained TTS (adaptive lead-in +
        question) can finish before silence timing begins.
        """
        try:
            # Wait for possible follow-on TTS chunks after this BotStopped.
            await asyncio.sleep(0.85)
            if self.bot_is_speaking:
                # Another chunk started; its BotStopped will reschedule.
                return
            if self.latest_user_transcript.strip():
                return

            self._awaiting_candidate_answer = True
            self._silence_stage = "watching"
            nudge_at = self.policy.candidate_silence_nudge_seconds
            rephrase_at = self.policy.candidate_silence_rephrase_seconds
            if rephrase_at <= nudge_at:
                rephrase_at = nudge_at + 0.5
            await asyncio.sleep(nudge_at)
            if not self._awaiting_candidate_answer:
                return
            if self.latest_user_transcript.strip():
                return
            logger.info("Candidate silence nudge after %.1fs", nudge_at)
            self._silence_nudge_sent = True
            self._silence_stage = "nudged"
            await self._speak_to_client(
                SILENCE_NUDGE_TEXT,
                FrameDirection.DOWNSTREAM,
                role="system",
            )

            remaining = rephrase_at - nudge_at
            if remaining > 0:
                await asyncio.sleep(remaining)
            if not self._awaiting_candidate_answer:
                return
            if self.latest_user_transcript.strip():
                return
            logger.info("Candidate silence rephrase after %.1fs", rephrase_at)
            self._silence_stage = "done"
            await self._speak_to_client(
                SILENCE_REPHRASE_TEXT,
                FrameDirection.DOWNSTREAM,
                role="system",
            )
            self._awaiting_candidate_answer = False
        except asyncio.CancelledError:
            logger.debug("Candidate silence watch cancelled — speech detected.")

    def _note_candidate_activity(self) -> None:
        """Cancel silence prompts once the candidate starts answering."""
        self._awaiting_candidate_answer = False
        self._silence_stage = None
        self._cancel_silence_watch()

    async def _emit_conversation(
        self, event: dict, direction: FrameDirection = FrameDirection.DOWNSTREAM
    ) -> None:
        """Push a conversation UI event downstream (does not affect dialogue)."""
        await self.push_frame(self.conversation.frame_for(event), direction)

    async def _emit_phase(self, phase: str, direction: FrameDirection) -> None:
        await self._emit_conversation(self.conversation.phase(phase), direction)

    async def _speak_to_client(
        self,
        text: str,
        direction: FrameDirection,
        *,
        role: str = "assistant",
        turn_id: str | None = None,
        emit_chat: bool = True,
    ) -> None:
        """Emit one finalized chat bubble (optional) then speak via TTS."""
        if not text:
            return
        if role in ("assistant", "system") and self._should_suppress_duplicate_tts(text):
            logger.info("Suppressing duplicate post-barge-in TTS: %r", text[:120])
            return
        if emit_chat:
            await self._emit_conversation(
                self.conversation.message(role=role, text=text, turn_id=turn_id),
                direction,
            )
        if role in ("assistant", "system"):
            self._last_spoken_assistant_text = text
        await self.push_frame(TTSSpeakFrame(text), direction)

    def _schedule_turn_debounce(self, delay_seconds: float | None = None) -> None:
        """Queue transcript evaluation after the configured debounce window."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        delay = self._compute_turn_debounce_delay(delay_seconds)
        self._debounce_task = asyncio.create_task(
            self._process_buffered_transcript_after_delay(delay)
        )

    def _in_resume_window(self) -> bool:
        return time.time() < self._resume_window_until

    def _open_resume_window(self, submitted_text: str) -> None:
        """Track a substantial submit so short tails can merge or be suppressed."""
        text = (submitted_text or "").strip()
        self._last_submitted_transcript = text
        self._last_submitted_word_count = len(text.split())
        self._resume_window_until = time.time() + self.policy.turn_resume_window_seconds

    def _compute_turn_debounce_delay(self, override: float | None = None) -> float:
        """Pick debounce delay; extend for substantial answers and resume tails."""
        buffered = getattr(self, "latest_user_transcript", "").strip()
        word_count = len(buffered.split())

        delay = (
            self.policy.final_transcript_debounce_seconds
            if override is None
            else override
        )

        if word_count >= self.policy.turn_tail_min_words_for_suspicion:
            delay = max(delay, self.policy.turn_resume_window_seconds)

        if self._in_resume_window():
            remaining = max(0.0, self._resume_window_until - time.time())
            delay = max(delay, remaining + 0.2)
        return delay

    def _looks_like_post_submit_tail(self, text: str) -> bool:
        """Short orphan STT tail arriving shortly after a substantial answer."""
        if not self._in_resume_window():
            return False
        if self._last_submitted_word_count < self.policy.turn_tail_min_words_for_suspicion:
            return False

        clean = (text or "").strip()
        if not clean:
            return True

        words = clean.split()
        if len(words) > self.policy.turn_tail_max_words:
            return False

        tail = clean.lower().strip(" .,!?'\"")
        last = (self._last_submitted_transcript or "").lower()
        if tail and tail in last:
            return True

        return len(words) <= self.policy.turn_tail_max_words

    async def _maybe_interrupt_bot(self, stt_hint: str = "") -> bool:
        """Barge-in when user speaks (VAD) or STT shows real words during bot TTS."""
        if not self.bot_is_speaking:
            return False
        spoken_for = (
            time.time() - self._bot_speech_started_at
            if self._bot_speech_started_at
            else 0.0
        )
        min_speak = self.policy.barge_in_min_bot_speak_seconds
        word_count = len((stt_hint or "").split())
        if spoken_for < min_speak and word_count < 3:
            logger.debug(
                "Ignoring early barge-in (spoken %.2fs, %d words)",
                spoken_for,
                word_count,
            )
            return False
        logger.info("User interrupted bot — broadcasting interruption")
        self.last_barge_in_at = time.time()
        self.barge_in_active = True
        self._barge_in_mic_allow_until = time.time() + self._barge_in_mic_allow_seconds
        self._barge_in_tts_suppress_until = time.time() + self._barge_in_settle_seconds + 2.0
        await self.broadcast_interruption()
        self.bot_is_speaking = False
        return True

    def _in_barge_in_mic_allow_window(self) -> bool:
        return self.barge_in_active or time.time() < self._barge_in_mic_allow_until

    def _should_suppress_duplicate_tts(self, text: str) -> bool:
        """Avoid re-speaking the interrupted question right after barge-in."""
        if time.time() >= getattr(self, "_barge_in_tts_suppress_until", 0):
            return False
        incoming = (text or "").strip().lower()
        previous = (getattr(self, "_last_spoken_assistant_text", "") or "").strip().lower()
        if not incoming or not previous:
            return False
        if incoming == previous:
            return True
        # Near-duplicate closing / repeat of same question
        if len(incoming) > 40 and (
            incoming in previous or previous in incoming
        ):
            return True
        return False

    @staticmethod
    def _is_tiny_trailing_fragment(text: str) -> bool:
        """Orphan 1–2 word STT afterthoughts that should not start a turn."""
        clean = (text or "").strip().lower().strip(" .,!?'\"")
        if not clean:
            return True
        words = clean.split()
        if len(words) > 2:
            return False
        keep = {
            "skip",
            "repeat",
            "pardon",
            "what",
            "yes",
            "no",
            "okay",
            "ok",
            "yeah",
        }
        if clean in keep:
            return False
        if any(
            p in clean
            for p in (
                "skip",
                "repeat",
                "previous",
                "next question",
                "don't know",
                "dont know",
            )
        ):
            return False
        return True

    @staticmethod
    def _is_check_in_or_junk(text: str) -> bool:
        """Mic checks / tiny barge-in fragments that should not start a dialogue turn."""
        clean = (text or "").strip().lower().strip(" .,!?'\"")
        if not clean:
            return True
        words = clean.split()
        check_ins = {
            "hello",
            "hello?",
            "hi",
            "hey",
            "so",
            "so hello",
            "so hello?",
            "hear me",
            "hear me?",
            "can you hear me",
            "can you hear me?",
            "are you there",
            "are you there?",
            "yes",
            "yeah",
            "ok",
            "okay",
        }
        if clean in check_ins:
            return True
        if len(words) < 5 and any(
            p in clean
            for p in (
                "hello",
                "hear me",
                "are you there",
                "can you hear",
                "testing",
                "mic check",
            )
        ):
            return True
        return False

    def _schedule_interim_finalize(self) -> None:
        """If VAD misses speech, finalize buffered interim STT after a short pause."""
        if self._interim_finalize_task and not self._interim_finalize_task.done():
            self._interim_finalize_task.cancel()
        self._interim_finalize_task = asyncio.create_task(
            self._finalize_buffered_interim_after_silence()
        )

    async def _finalize_buffered_interim_after_silence(self) -> None:
        try:
            await asyncio.sleep(self._interim_silence_seconds)
            if self.bot_is_speaking:
                return
            if self._in_resume_window():
                logger.debug(
                    "Interim silence fallback deferred — resume window active (%.2fs left)",
                    max(0.0, self._resume_window_until - time.time()),
                )
                return
            if self._user_vad_speaking:
                logger.debug(
                    "Interim silence fallback skipped — VAD still marks user as speaking"
                )
                return
            buffered = self.latest_user_transcript.strip()
            if not buffered:
                return
            word_count = len(buffered.split())
            # Prefer VAD-stop + final STT. Only submit interim as last resort when we
            # have a substantial utterance and the speaker is quiet.
            if not self._saw_final_stt_for_utterance and word_count < 12:
                logger.info(
                    "Interim STT silence fallback skipped — waiting for VAD/final "
                    "(%d words): %r",
                    word_count,
                    buffered[:120],
                )
                return
            if word_count < self._interim_min_words:
                logger.info(
                    "Interim STT silence fallback skipped — too short (%d words): %r",
                    word_count,
                    buffered[:120],
                )
                return
            logger.info(
                "Interim STT silence fallback — scheduling turn from buffered text: %r",
                buffered[:120],
            )
            self._schedule_turn_debounce(self.policy.transcript_debounce_seconds)
        except asyncio.CancelledError:
            logger.debug("Interim finalize task cancelled — new speech detected.")

    def _merge_transcript_part(self, user_text: str) -> None:
        """Accumulate partial STT chunks into one coherent utterance.

        Prefers replace-when-extends so progressive Deepgram interims do not
        concatenate into duplicated phrases.
        """
        from dialogue.transcript_utils import merge_stt_hypothesis

        user_text = (user_text or "").strip()
        if not user_text:
            return

        if not self.utterance_parts:
            self.utterance_parts = [user_text]
            self.latest_user_transcript = user_text
            return

        current = " ".join(self.utterance_parts).strip()
        merged = merge_stt_hypothesis(current, user_text)
        self.utterance_parts = [merged] if merged else []
        self.latest_user_transcript = merged

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
        # During barge-in mic-allow window, preserve candidate speech.
        if self._in_barge_in_mic_allow_window():
            return False
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

        # Drop orphan trailing STT fragments before dialogue.
        if self._is_tiny_trailing_fragment(user_text):
            logger.info("Discarding tiny trailing STT fragment quietly: %r", user_text)
            self._clear_transcript_buffer()
            return None

        if self._looks_like_post_submit_tail(user_text):
            logger.info(
                "Discarding post-submit tail fragment during resume window: %r",
                user_text,
            )
            self._clear_transcript_buffer()
            return None

        # Drop junk barge-in / mic-check fragments before dialogue (no guard storm).
        if self._in_barge_in_mic_allow_window() and (
            len(user_text.split()) < 5 or self._is_check_in_or_junk(user_text)
        ):
            logger.info(
                "Discarding short/check-in post-barge-in transcript quietly: %r",
                user_text,
            )
            self._clear_transcript_buffer()
            return None

        # Brief settle after barge-in so interrupted TTS echo does not fire a turn.
        if time.time() - self.last_barge_in_at < getattr(self, "_barge_in_settle_seconds", 0):
            if len(user_text.split()) < 5:
                logger.info(
                    "Discarding short transcript during barge-in settle: %r",
                    user_text,
                )
                self._clear_transcript_buffer()
                return None
        user_text = await self._apply_short_answer_grace(user_text)

        # Re-check after grace in case only a check-in arrived.
        if self._in_barge_in_mic_allow_window() and (
            len(user_text.split()) < 5 or self._is_check_in_or_junk(user_text)
        ):
            logger.info(
                "Discarding short/check-in transcript after grace quietly: %r",
                user_text,
            )
            self._clear_transcript_buffer()
            return None

        self._clear_transcript_buffer()
        self._saw_final_stt_for_utterance = False

        if self.policy.is_filler(user_text):
            logger.info("Ignoring filler transcript after grace: %r", user_text)
            return None
        if user_text == self.last_processed_transcript:
            logger.info("Duplicate transcript skipped: %r", user_text)
            return None

        return user_text

    async def _submit_turn(self, user_text: str, direction: FrameDirection) -> None:
        """Process one complete transcript through the adapter and push TTS response."""
        self._note_candidate_activity()
        # Ready for a new silence cycle after the next interview question finishes.
        self._silence_stage = None
        self.last_processed_transcript = user_text
        self.first_real_user_turn_seen = True
        self._open_resume_window(user_text)
        was_barge_in = self.barge_in_active
        turn_id = self.conversation.new_turn_id()

        logger.info("Processing user transcript: %r", user_text)
        if was_barge_in:
            logger.info("Transcript from barge-in turn — dialogue policy will classify.")

        await self._emit_conversation(
            self.conversation.message(role="user", text=user_text, turn_id=turn_id),
            direction,
        )
        await self._emit_phase("thinking", direction)

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
                await self._speak_to_client(
                    "I'm sorry, I had trouble processing that response. Could you please repeat?",
                    direction,
                    turn_id=turn_id,
                )
                return

            ai_text = sanitize_tts_text(response.get("ai_response_text", ""))
            is_complete = response.get("is_complete", False)

            if ai_text:
                await self._speak_to_client(
                    ai_text, direction, role="assistant", turn_id=turn_id
                )

            if is_complete:
                logger.info(
                    "Interview %s complete — spoken closing then EndTaskFrame.",
                    self.session_id,
                )
                closing_already = "concludes the interview" in (ai_text or "").lower()
                if not closing_already:
                    await self._speak_to_client(
                        INTERVIEW_CLOSING_SPOKEN,
                        direction,
                        role="system",
                        turn_id=turn_id,
                    )
                await asyncio.sleep(self.policy.closing_delay_seconds)
                await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

        except Exception:
            logger.exception("Failed to process turn in InterviewProcessor")
            await self._speak_to_client(
                "I'm sorry, I encountered an internal error. Let's try again.",
                direction,
                turn_id=turn_id,
            )

    async def _process_buffered_transcript_after_delay(
        self, delay_seconds: float | None = None
    ) -> None:
        try:
            delay = (
                self.policy.final_transcript_debounce_seconds
                if delay_seconds is None
                else delay_seconds
            )
            await asyncio.sleep(delay)

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

        if isinstance(frame, BotStartedSpeakingFrame) or isinstance(frame, BotSpeakingFrame):
            logger.debug("Bot started speaking — mic echo cooldown active")
            was_speaking = self.bot_is_speaking
            if not self.bot_is_speaking:
                self._bot_speech_started_at = time.time()
            self.bot_is_speaking = True
            # Preserve post-barge-in mic allow — don't re-arm long echo discard.
            if not self._in_barge_in_mic_allow_window():
                self.ignore_user_audio_until = (
                    time.time() + self.policy.bot_echo_cooldown_seconds
                )
            # Cancel settle debounce only — leave an active silence cycle alone
            # (silence nudge/rephrase also emit BotStartedSpeakingFrame).
            if self._silence_stage is None:
                self._cancel_silence_watch()

            if not self.first_real_user_turn_seen:
                self.startup_audio_ignore_until = max(
                    self.startup_audio_ignore_until,
                    time.time() + self.policy.startup_refresh_seconds,
                )
                logger.debug(
                    "Startup audio gate refreshed until %.1f",
                    self.startup_audio_ignore_until,
                )

            if not was_speaking and isinstance(frame, BotStartedSpeakingFrame):
                await self._emit_phase("speaking", direction)

            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            logger.debug("Bot stopped speaking — short mic echo cooldown")
            self.bot_is_speaking = False
            self._bot_speech_started_at = 0.0
            if self._in_barge_in_mic_allow_window():
                self.ignore_user_audio_until = (
                    time.time() + self._barge_in_echo_cooldown_seconds
                )
            else:
                self.ignore_user_audio_until = (
                    time.time() + self.policy.bot_stop_echo_cooldown_seconds
                )
            if not self.latest_user_transcript.strip():
                self._schedule_silence_watch()
            await self._emit_phase("listening", direction)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            logger.debug("VAD: user started speaking")
            self.vad_enabled = True
            self._user_vad_speaking = True
            self._saw_final_stt_for_utterance = False
            self._note_candidate_activity()
            if self.bot_is_speaking:
                await self._maybe_interrupt_bot()

            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()
                logger.debug("Cancelled debounce task — user speaking again")
            if self._interim_finalize_task and not self._interim_finalize_task.done():
                self._interim_finalize_task.cancel()

            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            logger.debug("VAD: user stopped speaking")
            self.vad_enabled = True
            self._user_vad_speaking = False

            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()

            self._schedule_turn_debounce()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterimTranscriptionFrame):
            interim_text = (getattr(frame, "text", "") or "").strip()
            if interim_text:
                if self.bot_is_speaking:
                    await self._maybe_interrupt_bot(interim_text)
                    self._merge_transcript_part(interim_text)
                elif not self.bot_is_speaking:
                    self._note_candidate_activity()
                    self._merge_transcript_part(interim_text)
                    logger.debug("Buffered interim STT: %r", interim_text[:120])
                    self._schedule_interim_finalize()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            user_text = (frame.text or "").strip()

            if getattr(frame, "finalized", True) is False:
                if user_text and not self.bot_is_speaking:
                    self._note_candidate_activity()
                    self._merge_transcript_part(user_text)
                    logger.debug("Stored non-final transcription: %r", user_text)
                    self._schedule_interim_finalize()
                await self.push_frame(frame, direction)
                return

            if self.bot_is_speaking:
                if user_text:
                    await self._maybe_interrupt_bot(user_text)
                    self._merge_transcript_part(user_text)
                    logger.debug("Stored transcript while bot speaking: %r", user_text)
                return

            if not user_text:
                logger.warning("Empty final transcript — requesting clarification.")
                await self._speak_to_client(
                    "I didn't catch that. Could you please repeat or elaborate?",
                    direction,
                    role="system",
                )
                return

            self._note_candidate_activity()
            self._merge_transcript_part(user_text)
            self._saw_final_stt_for_utterance = True
            logger.info("Final STT transcript received: %r", user_text[:160])

            if self._in_resume_window() and self._looks_like_post_submit_tail(
                getattr(self, "latest_user_transcript", "")
            ):
                logger.info(
                    "Resume window: deferring likely tail fragment instead of immediate turn"
                )
                delay = self._compute_turn_debounce_delay(
                    self.policy.final_transcript_debounce_seconds + 0.2
                )
            else:
                delay = self._compute_turn_debounce_delay()
            self._schedule_turn_debounce(delay)
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)
