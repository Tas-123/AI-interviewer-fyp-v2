"""
InterviewProcessor — Custom Pipecat FrameProcessor that bridges the Pipecat STT/TTS pipeline
with the existing InterviewDialogueAdapter.
"""

import logging
import asyncio

logger = logging.getLogger("InterviewProcessor")


def sanitize_tts_text(text: str) -> str:
    """
    Checks if the given TTS text represents a Gemini generation or quota error.
    If so, logs the original text at WARNING level and replaces it with a clean fallback.
    """
    if not text:
        return text
    # Remove internal/debug labels from spoken TTS only.
    # Keep the actual follow-up question unchanged.
    text = text.replace("[Follow-up]", "")
    text = text.replace("[follow-up]", "")
    text = text.replace("Follow-up:", "")
    text = text.replace("follow-up:", "")
    text = text.strip()
    if text.startswith("[Error") or "Error generating question" in text:
        logger.warning(f"Gemini error detected in TTS path: '{text}'. Substituting manual-testing fallback greeting.")
        return "Welcome to the interview. Please briefly introduce yourself and tell me what kind of role or area you would like this interview to focus on."
    return text

try:
    from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
    from pipecat.frames.frames import (
        Frame, TextFrame, TranscriptionFrame, EndTaskFrame, TTSSpeakFrame,
        InterimTranscriptionFrame, VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame,
        BotStartedSpeakingFrame, BotStoppedSpeakingFrame, BotSpeakingFrame, InterruptionFrame
    )
except ImportError:
    logger.warning("Pipecat-ai not installed in this environment. Using mock definitions for dry-run/testing.")
    
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
        def __init__(self, text: str, user_id: str = "test-user", timestamp: str = "0", language = None, result = None, finalized: bool = True):
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
    class InterruptionFrame(Frame):
        pass
class InterviewProcessor(FrameProcessor):
    """
    FrameProcessor that intercepts user speech transcripts (TranscriptionFrame),
    queries the dialogue adapter, and pushes the AI's response text (TextFrame)
    downstream to the TTS engine.
    """
    def __init__(self, adapter, session_id: str):
        super().__init__()
        self.adapter = adapter
        self.session_id = session_id
        self.last_processed_transcript = ""
        self.latest_user_transcript = ""
        self.utterance_parts = []

        # Prevent bot/TTS echo from being processed as candidate speech.
        self.bot_is_speaking = False
        self.ignore_user_audio_until = 0.0
        self.bot_is_speaking = False
        self.vad_enabled = False
        self._debounce_task = None

        # Barge-in tracking:
        # When candidate interrupts while bot is speaking, we mark it so the
        # transcript can later be classified instead of blindly scored.
        self.last_barge_in_at = 0.0
        self.barge_in_active = False

        # Startup audio gate:
        # Prevent early mic/background/ChatGPT audio from becoming the first answer
        # while the intro greeting is being generated/spoken.
        import time
        self.startup_audio_ignore_until = time.time() + 4.0
        self.first_real_user_turn_seen = False
    
    def _merge_transcript_part(self, user_text: str):
        """
        Store transcript parts without losing earlier speech.
        Deepgram sometimes sends partial phrases, then later sends another phrase.
        This keeps the longest useful sequence instead of only the last chunk.
        """
        user_text = (user_text or "").strip()
        if not user_text:
            return

        if not self.utterance_parts:
            self.utterance_parts.append(user_text)
            self.latest_user_transcript = user_text
            return

        current = " ".join(self.utterance_parts).strip()

        # If new text already contains the current text, replace with the better longer text.
        if current and current.lower() in user_text.lower():
            self.utterance_parts = [user_text]
            self.latest_user_transcript = user_text
            return

        # If current already contains the new text, ignore duplicate/shorter update.
        if user_text.lower() in current.lower():
            self.latest_user_transcript = current
            return

        # Otherwise append the new phrase.
        self.utterance_parts.append(user_text)
        self.latest_user_transcript = " ".join(self.utterance_parts).strip()

    def _clean_transcript_for_evaluation(self, text: str) -> str:
        """
        Strong cleanup for ASR/interim transcript repetition.
        Removes repeated adjacent fragments while preserving candidate meaning.
        """
        import re

        original = (text or "").strip()
        if not original:
            return ""

        cleaned = re.sub(r"\s+", " ", original).strip()
        cleaned = cleaned.replace(" ,", ",").replace(" .", ".")

        def remove_adjacent_repeated_ngrams(tokens, max_n=12):
            if not tokens:
                return tokens

            changed = True
            while changed:
                changed = False
                n_limit = min(max_n, len(tokens) // 2)

                for n in range(n_limit, 0, -1):
                    i = 0
                    result = []

                    while i < len(tokens):
                        current = tokens[i:i+n]
                        nxt = tokens[i+n:i+(2*n)]

                        current_norm = [x.lower().strip(".,!?") for x in current]
                        nxt_norm = [x.lower().strip(".,!?") for x in nxt]

                        if len(current) == n and current_norm == nxt_norm:
                            result.extend(current)
                            i += 2 * n
                            changed = True

                            while i + n <= len(tokens):
                                extra = tokens[i:i+n]
                                extra_norm = [x.lower().strip(".,!?") for x in extra]
                                if extra_norm == current_norm:
                                    i += n
                                else:
                                    break
                        else:
                            result.append(tokens[i])
                            i += 1

                    tokens = result

            return tokens

        def remove_overlapping_repeated_phrases(text_value):
            words = text_value.split()
            if len(words) < 8:
                return text_value

            changed = True
            while changed:
                changed = False
                words = text_value.split()

                for n in range(min(14, len(words)//2), 3, -1):
                    i = 0
                    result = []

                    while i < len(words):
                        current = [w.lower().strip(".,!?") for w in words[i:i+n]]

                        found = False
                        for shift in range(1, min(n, len(words) - i - n) + 1):
                            candidate = [w.lower().strip(".,!?") for w in words[i+shift:i+shift+n]]
                            if current == candidate:
                                result.extend(words[i:i+shift])
                                i = i + shift
                                found = True
                                changed = True
                                break

                        if not found:
                            result.append(words[i])
                            i += 1

                    new_text = " ".join(result)
                    if new_text != text_value:
                        text_value = new_text
                        break

            return text_value

        tokens = cleaned.split()

        # Remove exact adjacent repeated chunks.
        tokens = remove_adjacent_repeated_ngrams(tokens)
        cleaned = " ".join(tokens)

        # Remove repeated single adjacent words: "the the" -> "the"
        cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE).strip()

        # Remove repeated medium phrases:
        phrase_pattern = re.compile(
            r"\b((?:\w+[,.]?\s+){2,10}\w+[,.]?)(?:\s+\1\b)+",
            flags=re.IGNORECASE
        )

        previous = None
        while previous != cleaned:
            previous = cleaned
            cleaned = phrase_pattern.sub(r"\1", cleaned).strip()

        cleaned = remove_overlapping_repeated_phrases(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return original

        original_word_count = len(original.split())
        cleaned_word_count = len(cleaned.split())

        # Safety: don't destroy meaningful answers.
        if original_word_count >= 10 and cleaned_word_count < max(5, int(original_word_count * 0.40)):
            return original

        return cleaned


    async def _process_buffered_transcript_after_delay(self):
        try:
            # Debounce delay: give the candidate enough time to finish natural
            # pauses before treating the buffered transcript as complete.
            await asyncio.sleep(3.0)

            if getattr(self, "bot_is_speaking", False):
                logger.info("Bot is still speaking, but processing saved user transcript after debounce.")

            user_text = getattr(self, "latest_user_transcript", "").strip()
            if not user_text:
                logger.info("Debounce completed but latest_user_transcript is empty. Ignoring.")
                return

            # Startup audio gate:
            # Ignore early background/side audio captured during intro startup.
            try:
                import time
                if (
                    not getattr(self, "first_real_user_turn_seen", False)
                    and time.time() < getattr(self, "startup_audio_ignore_until", 0.0)
                ):
                    logger.info(f"Ignoring startup transcript before interview is ready: '{user_text}'")
                    self.latest_user_transcript = ""
                    self.utterance_parts = []
                    return
            except Exception:
                pass

            # Drop likely TTS echo captured immediately after bot speaks.
            try:
                import time
                if time.time() < getattr(self, "ignore_user_audio_until", 0.0):
                    logger.info(f"Ignoring transcript during bot echo cooldown: '{user_text}'")
                    self.latest_user_transcript = ""
                    self.utterance_parts = []
                    return
            except Exception:
                pass

            # Ignore tiny filler transcripts that should not become full interview turns
            filler_words = {"ok", "okay", "yes", "yeah", "yep", "hmm", "um", "uh", "alright", "right"}
            if user_text.lower().strip(" .,!?'\"") in filler_words:
                logger.info(f"Ignoring filler transcript after debounce: '{user_text}'")
                return

            # If this utterance came right after a barge-in, log it clearly.
            # The DialogueManager will classify clarification/off-topic/answer.
            if getattr(self, "barge_in_active", False):
                logger.info(f"Processing transcript captured after barge-in: '{user_text}'")

            # Light-clean ASR repetition before evaluation/dialogue manager.
            cleaned_user_text = self._clean_transcript_for_evaluation(user_text)
            if cleaned_user_text != user_text:
                logger.info(f"Cleaned transcript for evaluation: '{cleaned_user_text}'")
                user_text = cleaned_user_text

            # Short-transcript grace period:
            # If the assembled transcript is very short (≤6 words), the candidate
            # is likely still mid-sentence (e.g. "Worked on a project").
            # Wait an extra period for more speech before finalizing.
            word_count = len(user_text.split())
            if word_count <= 6:
                logger.info(f"Short transcript ({word_count} words), waiting extra grace period: '{user_text}'")
                await asyncio.sleep(2.5)
                # Check if more speech arrived during the grace period
                updated = getattr(self, "latest_user_transcript", "").strip()
                if updated and updated != user_text:
                    cleaned_updated = self._clean_transcript_for_evaluation(updated)
                    if cleaned_updated:
                        logger.info(f"Extended transcript after grace: '{cleaned_updated}'")
                        user_text = cleaned_updated

            # Clear buffer so it is not processed twice
            self.latest_user_transcript = ""
            self.utterance_parts = []
            # Duplicate guard: if transcript text equals last_processed_transcript, skip it
            if user_text == self.last_processed_transcript:
                logger.info(f"Duplicate transcript detected and skipped: '{user_text}'")
                return
            # Ignore tiny filler transcripts that should not become full interview turns
            filler_words = {"ok", "okay", "yes", "yeah", "yep", "hmm", "um", "uh", "alright", "right"}
            if user_text.lower().strip(" .,!?'\"") in filler_words:
                logger.info(f"Ignoring filler transcript in non-VAD mode: '{user_text}'")
                return

            self.last_processed_transcript = user_text
            self.first_real_user_turn_seen = True
            was_barge_in = getattr(self, "barge_in_active", False)
            logger.info(f"Processing complete user transcript: '{user_text}'")
            if was_barge_in:
                logger.info("This transcript came from a barge-in turn and will be handled by dialogue policy.")

            try:
                # Call dialogue adapter to process text and get next question
                response = self.adapter.process_user_text(self.session_id, user_text)

                # Reset barge-in state after this transcript has been handed to dialogue policy.
                if getattr(self, "barge_in_active", False):
                    logger.info("Resetting barge-in state after transcript processing.")
                    self.barge_in_active = False

                if response.get("error"):
                    logger.error(f"Adapter error: {response['error']}")
                    # Fallback spoken message
                    await self.push_frame(
                        TTSSpeakFrame("I'm sorry, I had trouble processing that response. Could you please repeat?"),
                        FrameDirection.DOWNSTREAM
                    )
                else:
                    ai_text = response.get("ai_response_text", "")
                    is_complete = response.get("is_complete", False)

                    # Check for Gemini error/quota fallback
                    ai_text = sanitize_tts_text(ai_text)

                    # Speak response through TTS by pushing TTSSpeakFrame
                    if ai_text:
                        await self.push_frame(TTSSpeakFrame(ai_text), FrameDirection.DOWNSTREAM)

                    # Handle graceful pipeline shutdown when interview wraps up
                    if is_complete:
                        logger.info(f"Interview {self.session_id} marked as complete. Sending spoken closing before ending.")
                        closing_text = "Thank you for your time. This concludes the interview. Your final report is now being generated."
                        await self.push_frame(TTSSpeakFrame(closing_text), FrameDirection.DOWNSTREAM)
                        await asyncio.sleep(2.5)
                        await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

            except Exception as e:
                logger.exception("Failed to process turn in InterviewProcessor")
                await self.push_frame(
                    TTSSpeakFrame("I'm sorry, I encountered an internal error. Let's try again."),
                    FrameDirection.DOWNSTREAM
                )
        except asyncio.CancelledError:
            logger.info("Debounce task cancelled because user started speaking again.")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # 1. Always call super().process_frame first
        await super().process_frame(frame, direction)

        # Log every frame type received (this is the diagnostic heartbeat)
        logger.info(f"process_frame: Received frame type: {type(frame).__name__} (direction: {direction})")

        # Track bot speaking state and briefly ignore mic input to avoid TTS echo
        if isinstance(frame, (BotStartedSpeakingFrame, BotSpeakingFrame)):
            import time
            logger.info(f"Bot started speaking: {type(frame).__name__} ? mic echo cooldown active")
            self.bot_is_speaking = True
            self.ignore_user_audio_until = time.time() + 1.2

            # Startup gate refresh:
            # Keep the first-turn audio guard alive while the first intro/question
            # is being spoken, because __init__ timing can expire before real TTS.
            if not getattr(self, "first_real_user_turn_seen", False):
                self.startup_audio_ignore_until = max(
                    getattr(self, "startup_audio_ignore_until", 0.0),
                    time.time() + 3.0
                )
                logger.info(
                    f"Startup audio gate refreshed during first bot speech until {self.startup_audio_ignore_until}"
                )

            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            import time
            logger.info("Bot stopped speaking ? short mic echo cooldown active")
            self.bot_is_speaking = False
            self.ignore_user_audio_until = time.time() + 0.8
            await self.push_frame(frame, direction)
            return

        # 2. Explicit VAD event logging — if these never appear, VAD is not triggering
        if isinstance(frame, VADUserStartedSpeakingFrame):
            logger.info("VAD EVENT: VADUserStartedSpeakingFrame — user started speaking")
            self.vad_enabled = True
            if getattr(self, "bot_is_speaking", False):
                import time
                logger.info("User interrupted while bot was speaking. Broadcasting interruption.")
                self.last_barge_in_at = time.time()
                self.barge_in_active = True
                await self.broadcast_interruption()
                self.bot_is_speaking = False

            # Cancel any pending debounce task since the user started speaking again
            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()
                logger.info("VAD user started speaking. Resetting debounce task.")

            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            logger.info("VAD EVENT: VADUserStoppedSpeakingFrame — user stopped speaking (Deepgram Finalize will be sent)")
            self.vad_enabled = True

            # Cancel any existing debounce task to avoid duplicate/overlapping tasks
            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()

            # Schedule a new debounce task
            logger.info("VAD stopped, waiting for final transcript debounce")
            self._debounce_task = asyncio.create_task(self._process_buffered_transcript_after_delay())

            await self.push_frame(frame, direction)
            return

        # 3. Log interim transcriptions — if these appear, Deepgram IS returning results
        if isinstance(frame, InterimTranscriptionFrame):
            interim_text = (getattr(frame, "text", "") or "").strip()
            logger.info(f"DEEPGRAM INTERIM: '{interim_text}' (not yet finalized)")

            # Keep interim transcript as fallback because some STT providers may emit
            # the fuller sentence in interim frames and only a short final fragment later.
            if interim_text:
                self._merge_transcript_part(interim_text)
                logger.info(f"Buffered interim transcript fallback: '{interim_text}'")

            await self.push_frame(frame, direction)
            return

        # 4. Intercept transcription frames flowing downstream from STT
        if isinstance(frame, TranscriptionFrame):
            # Specifically log when TranscriptionFrame is received
            logger.info(f"process_frame: Received TranscriptionFrame. text: '{getattr(frame, 'text', '')}', finalized: {getattr(frame, 'finalized', None)}")

            user_text = (frame.text or "").strip()

            # Do not process non-final STT chunks immediately.
            # Keep the latest partial transcript as a fallback in case no final transcript arrives.
            if getattr(frame, "finalized", True) is False:
                if user_text:
                    self._merge_transcript_part(user_text)
                    logger.info(f"Stored non-final transcription as fallback: '{user_text}'")
                await self.push_frame(frame, direction)
                return

            if getattr(self, "bot_is_speaking", False):
                if user_text:
                    self._merge_transcript_part(user_text)
                    logger.info(f"Stored transcript while bot was speaking: '{user_text}'")
                return

            # If VAD is active, buffer the transcript and wait for VAD stopped trigger
            if getattr(self, "vad_enabled", False):
                if not user_text:
                    logger.warning("Empty transcript received in VAD mode. Ignoring.")
                    return
                self._merge_transcript_part(user_text)
                logger.info(f"Buffered transcript: '{user_text}'")
                return

            # If VAD is not active (i.e. unit tests), process immediately to maintain compatibility
            # Handle empty/whitespace transcripts in non-VAD mode by requesting clarification
            if not user_text:
                logger.warning("Empty transcript received (non-VAD mode). Requesting clarification.")
                await self.push_frame(
                    TTSSpeakFrame("I didn't catch that. Could you please repeat or elaborate?"),
                    direction
                )
                return

            # Duplicate guard: if transcript text equals last_processed_transcript, skip it
            if user_text == self.last_processed_transcript:
                logger.info(f"Duplicate transcript detected and skipped in non-VAD mode: '{user_text}'")
                return

            self.last_processed_transcript = user_text
            logger.info(f"Received user transcript: '{user_text}'")

            try:
                # Call dialogue adapter to process text and get next question
                response = self.adapter.process_user_text(self.session_id, user_text)

                if response.get("error"):
                    logger.error(f"Adapter error: {response['error']}")
                    # Fallback spoken message
                    await self.push_frame(
                        TTSSpeakFrame("I'm sorry, I had trouble processing that response. Could you please repeat?"),
                        direction
                    )
                else:
                    ai_text = response.get("ai_response_text", "")
                    is_complete = response.get("is_complete", False)

                    # Check for Gemini error/quota fallback
                    ai_text = sanitize_tts_text(ai_text)

                    # Speak response through TTS by pushing TTSSpeakFrame
                    if ai_text:
                        await self.push_frame(TTSSpeakFrame(ai_text), direction)

                    # Handle graceful pipeline shutdown when interview wraps up
                    if is_complete:
                        logger.info(f"Interview {self.session_id} marked as complete. Sending spoken closing before ending.")
                        closing_text = "Thank you for your time. This concludes the interview. Your final report is now being generated."
                        await self.push_frame(TTSSpeakFrame(closing_text), FrameDirection.DOWNSTREAM)
                        await asyncio.sleep(2.5)
                        await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

            except Exception as e:
                logger.exception("Failed to process turn in InterviewProcessor")
                await self.push_frame(
                    TTSSpeakFrame("I'm sorry, I encountered an internal error. Let's try again."),
                    direction
                )
        else:
            # Pass all other frames through unchanged
            await self.push_frame(frame, direction)
