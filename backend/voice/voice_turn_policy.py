"""
Voice turn policy — configurable timing and gating for the Pipecat processor.

Phase 5: centralizes debounce, grace, echo cooldown, and filler-word rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Settings


DEFAULT_FILLER_WORDS = frozenset({
    "ok", "okay", "yes", "yeah", "yep", "hmm", "um", "uh", "alright", "right",
})

SILENCE_NUDGE_TEXT = (
    "Take your time — whenever you're ready to answer."
)
SILENCE_REPHRASE_TEXT = (
    "Are you still there? Feel free to answer when ready, "
    "or say next question if you'd like to move on."
)


@dataclass(frozen=True)
class VoiceTurnPolicy:
    """Timing and gating constants for live voice turn-taking."""

    transcript_debounce_seconds: float
    short_answer_grace_seconds: float
    short_answer_word_threshold: int
    startup_audio_gate_seconds: float
    startup_refresh_seconds: float
    bot_echo_cooldown_seconds: float
    bot_stop_echo_cooldown_seconds: float
    closing_delay_seconds: float
    candidate_silence_nudge_seconds: float
    candidate_silence_rephrase_seconds: float
    barge_in_min_bot_speak_seconds: float
    final_transcript_debounce_seconds: float
    filler_words: frozenset[str]

    @classmethod
    def from_settings(cls, cfg: "Settings") -> "VoiceTurnPolicy":
        return cls(
            transcript_debounce_seconds=cfg.transcript_debounce_seconds,
            short_answer_grace_seconds=cfg.short_answer_grace_seconds,
            short_answer_word_threshold=cfg.short_answer_word_threshold,
            startup_audio_gate_seconds=cfg.startup_audio_gate_seconds,
            startup_refresh_seconds=cfg.startup_refresh_seconds,
            bot_echo_cooldown_seconds=cfg.bot_echo_cooldown_seconds,
            bot_stop_echo_cooldown_seconds=cfg.bot_stop_echo_cooldown_seconds,
            closing_delay_seconds=cfg.closing_delay_seconds,
            candidate_silence_nudge_seconds=cfg.candidate_silence_nudge_seconds,
            candidate_silence_rephrase_seconds=cfg.candidate_silence_rephrase_seconds,
            barge_in_min_bot_speak_seconds=cfg.barge_in_min_bot_speak_seconds,
            final_transcript_debounce_seconds=cfg.final_transcript_debounce_seconds,
            filler_words=DEFAULT_FILLER_WORDS,
        )

    def is_filler(self, text: str) -> bool:
        normalized = (text or "").lower().strip(" .,!?\"'")
        return normalized in self.filler_words

    def is_short_answer(self, text: str) -> bool:
        return len((text or "").split()) <= self.short_answer_word_threshold
