"""
Shared ASR transcript cleanup for DialogueManager and voice processor.

Removes repeated n-grams and phrase echoes while preserving candidate meaning.
Phase 6B: stutter-prefix removal + quality assessment hook.
"""

from __future__ import annotations

import re

from dialogue.transcript_quality import TranscriptQuality, assess_transcript_quality


def _norm_token(token: str) -> str:
    t = token.lower().strip(".,!?;:")
    for suffix in (
        "'d", "'s", "'ll", "'ve", "'re", "'m",
        "\u2019d", "\u2019s", "\u2019ll", "\u2019ve", "\u2019re", "\u2019m",
    ):
        if t.endswith(suffix):
            return t[: -len(suffix)]
    return t


def _remove_adjacent_repeated_ngrams(tokens: list[str], max_n: int = 14) -> list[str]:
    changed = True
    while changed:
        changed = False
        for n in range(min(max_n, len(tokens) // 2), 0, -1):
            i = 0
            out: list[str] = []
            while i < len(tokens):
                cur = tokens[i : i + n]
                nxt = tokens[i + n : i + 2 * n]
                if len(cur) == n and [_norm_token(x) for x in cur] == [
                    _norm_token(x) for x in nxt
                ]:
                    out.extend(cur)
                    i += 2 * n
                    changed = True
                    while i + n <= len(tokens) and [
                        _norm_token(x) for x in tokens[i : i + n]
                    ] == [_norm_token(x) for x in cur]:
                        i += n
                else:
                    out.append(tokens[i])
                    i += 1
            tokens = out
    return tokens


def _remove_overlapping_repeated_phrases(text_value: str) -> str:
    words = text_value.split()
    if len(words) < 8:
        return text_value

    changed = True
    while changed:
        changed = False
        words = text_value.split()
        for n in range(min(14, len(words) // 2), 3, -1):
            i = 0
            result: list[str] = []
            while i < len(words):
                current = [w.lower().strip(".,!?") for w in words[i : i + n]]
                found = False
                for shift in range(1, min(n, len(words) - i - n) + 1):
                    candidate = [
                        w.lower().strip(".,!?") for w in words[i + shift : i + shift + n]
                    ]
                    if current == candidate:
                        result.extend(words[i : i + shift])
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


def _collapse_progressive_interim_phrases(text_value: str) -> str:
    """
    Collapse Deepgram interim restarts where each chunk extends the prior phrase.
    E.g. 'was doing was doing a project on ASR' -> 'was doing a project on ASR'.
    """
    words = text_value.split()
    if len(words) < 6:
        return text_value

    i = 0
    out: list[str] = []
    while i < len(words):
        merged = False
        for n in range(min(12, (len(words) - i) // 2), 1, -1):
            a = [w.lower().strip(".,!?") for w in words[i : i + n]]
            b = [w.lower().strip(".,!?") for w in words[i + n : i + 2 * n]]
            if a == b:
                out.extend(words[i : i + n])
                i += 2 * n
                while i + n <= len(words) and [
                    w.lower().strip(".,!?") for w in words[i : i + n]
                ] == a:
                    i += n
                merged = True
                break
        if not merged:
            out.append(words[i])
            i += 1
    return " ".join(out)


def _prefer_longest_overlapping_segment(parts: list[str]) -> str:
    """When STT emits overlapping finals, keep the longest coherent segment."""
    cleaned = [p.strip() for p in parts if p and p.strip()]
    if not cleaned:
        return ""
    best = cleaned[0]
    for part in cleaned[1:]:
        lower_best = best.lower()
        lower_part = part.lower()
        if lower_best in lower_part:
            best = part
        elif lower_part not in lower_best:
            best = f"{best} {part}".strip()
    return best


def _remove_stutter_prefix(text_value: str) -> str:
    """Remove duplicated opening phrases from partial STT restarts."""
    words = text_value.split()
    if len(words) < 6:
        return text_value

    for n in (4, 3, 2):
        if len(words) < n * 2:
            continue
        first = [w.lower().strip(".,!?") for w in words[:n]]
        second = [w.lower().strip(".,!?") for w in words[n : n * 2]]
        if first == second:
            return " ".join(words[n:])
    return text_value


def clean_live_transcript(text: str) -> str:
    """Clean repeated ASR fragments before evaluation and reporting."""
    original = (text or "").strip()
    if not original:
        return ""

    cleaned = re.sub(r"\s+", " ", original).strip()
    cleaned = cleaned.replace(" ,", ",").replace(" .", ".")
    cleaned = _collapse_progressive_interim_phrases(cleaned)
    cleaned = _remove_stutter_prefix(cleaned)

    tokens = _remove_adjacent_repeated_ngrams(cleaned.split())
    cleaned = " ".join(tokens)

    phrase_pattern = re.compile(
        r"\b((?:\w+[,.]?\s+){2,12}\w+[,.]?)(?:\s+\1\b)+",
        flags=re.IGNORECASE,
    )
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = phrase_pattern.sub(r"\1", cleaned).strip()

    cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = _remove_overlapping_repeated_phrases(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return original

    if len(original.split()) >= 10 and len(cleaned.split()) < max(
        5, int(len(original.split()) * 0.40)
    ):
        return original

    return cleaned


def prepare_transcript_for_evaluation(text: str) -> tuple[str, TranscriptQuality]:
    """Clean transcript and return quality assessment for evaluation fairness."""
    raw = (text or "").strip()
    cleaned = clean_live_transcript(raw)
    quality = assess_transcript_quality(raw, cleaned)
    return cleaned, quality
