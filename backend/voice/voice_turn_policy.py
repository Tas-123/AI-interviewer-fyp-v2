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
            filler_words=DEFAULT_FILLER_WORDS,
        )

    def is_filler(self, text: str) -> bool:
        normalized = (text or "").lower().strip(" .,!?\"'")
        return normalized in self.filler_words

    def is_short_answer(self, text: str) -> bool:
        return len((text or "").split()) <= self.short_answer_word_threshold
