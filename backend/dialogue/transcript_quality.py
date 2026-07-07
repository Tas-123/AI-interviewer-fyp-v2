"""
Transcript quality assessment — detect noisy STT before evaluation.

Phase 6B: separates speech-recognition artifacts from candidate intent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptQuality:
    """Quality signals for one candidate utterance."""

    raw_word_count: int
    cleaned_word_count: int
    reduction_ratio: float
    repeated_token_ratio: float
    stutter_prefix: bool
    noise_score: float
    is_noisy: bool
    flags: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "raw_word_count": self.raw_word_count,
            "cleaned_word_count": self.cleaned_word_count,
            "reduction_ratio": round(self.reduction_ratio, 3),
            "repeated_token_ratio": round(self.repeated_token_ratio, 3),
            "stutter_prefix": self.stutter_prefix,
            "noise_score": round(self.noise_score, 3),
            "is_noisy": self.is_noisy,
            "flags": list(self.flags),
        }


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", (text or "").strip()) if t]


def _repeated_token_ratio(tokens: list[str]) -> float:
    if len(tokens) < 4:
        return 0.0
    seen: dict[str, int] = {}
    repeats = 0
    for tok in tokens:
        key = tok.lower().strip(".,!?;:'\"")
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            repeats += 1
    return repeats / len(tokens)


def _has_stutter_prefix(text: str) -> bool:
    """Detect false starts like 'Well, I Well, about me'."""
    words = _tokenize(text)
    if len(words) < 6:
        return False
    for n in (2, 3, 4):
        if len(words) < n * 2:
            continue
        a = [w.lower().strip(".,!?") for w in words[:n]]
        b = [w.lower().strip(".,!?") for w in words[n : n * 2]]
        if a == b:
            return True
    return False


def assess_transcript_quality(raw: str, cleaned: str) -> TranscriptQuality:
    """Score how likely STT noise dominates the transcript."""
    raw_tokens = _tokenize(raw)
    clean_tokens = _tokenize(cleaned)
    raw_n = len(raw_tokens)
    clean_n = len(clean_tokens)

    reduction = 0.0
    if raw_n > 0:
        reduction = max(0.0, (raw_n - clean_n) / raw_n)

    rep_ratio = _repeated_token_ratio(raw_tokens)
    stutter = _has_stutter_prefix(raw)
    flags: list[str] = []

    if reduction >= 0.20:
        flags.append("high_cleanup_reduction")
    if rep_ratio >= 0.22:
        flags.append("repeated_tokens")
    if stutter:
        flags.append("stutter_prefix")
    if raw_n >= 12 and clean_n < max(5, int(raw_n * 0.45)):
        flags.append("over_compressed")

    noise_score = min(
        1.0,
        (reduction * 0.45)
        + (rep_ratio * 0.40)
        + (0.20 if stutter else 0.0)
        + (0.15 if "over_compressed" in flags else 0.0),
    )
    is_noisy = noise_score >= 0.42 or len(flags) >= 2

    return TranscriptQuality(
        raw_word_count=raw_n,
        cleaned_word_count=clean_n,
        reduction_ratio=reduction,
        repeated_token_ratio=rep_ratio,
        stutter_prefix=stutter,
        noise_score=noise_score,
        is_noisy=is_noisy,
        flags=tuple(flags),
    )
