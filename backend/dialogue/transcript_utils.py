"""
Shared ASR transcript cleanup for DialogueManager and voice processor.

Removes repeated n-grams and phrase echoes while preserving candidate meaning.
"""

from __future__ import annotations

import re


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


def clean_live_transcript(text: str) -> str:
    """Clean repeated ASR fragments before evaluation and reporting."""
    original = (text or "").strip()
    if not original:
        return ""

    cleaned = re.sub(r"\s+", " ", original).strip()
    cleaned = cleaned.replace(" ,", ",").replace(" .", ".")

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
