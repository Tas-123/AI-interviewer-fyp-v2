"""
Bounded recovery rephrase — same intent, fresh wording, no prompt stacking.

Used by repeat / clarify / redirect / IDK simplify recoveries.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

RecoveryMode = Literal["repeat", "clarify", "redirect", "simplify"]

_MODE_PREFIX = {
    "repeat": "Happy to repeat.",
    "clarify": "I'll ask it another way.",
    "redirect": "Let's focus on this.",
    "simplify": "That's okay — let me ask it more simply.",
}


def resolve_core_question(interview_context=None, last_question: str = "") -> str:
    """Return the single clean question to recover with."""
    if interview_context is not None and hasattr(
        interview_context, "get_active_canonical_question"
    ):
        return interview_context.get_active_canonical_question(last_question)
    from dialogue.guards.echo_guard import canonicalize_for_store

    return canonicalize_for_store(last_question)


def fallback_recovery_line(mode: RecoveryMode, core: str) -> str:
    """Single-paste fallback — never nests prior wrappers."""
    prefix = _MODE_PREFIX.get(mode, "Happy to repeat.")
    core = (core or "").strip()
    if not core:
        return f"{prefix} Please answer the current interview question in your own words."
    return f"{prefix} {core}"


def rephrase_recovery(
    *,
    core_question: str,
    domain: str = "",
    mode: RecoveryMode = "repeat",
    llm_client=None,
    llm_model: str = "",
) -> str:
    """
    Produce one short spoken recovery line for the same intent.

    Constraints: same topic, one question, no coaching, no stacking.
    """
    core = (core_question or "").strip()
    if not core:
        return fallback_recovery_line(mode, "")

    if llm_client is None:
        return fallback_recovery_line(mode, core)

    mode_instruction = {
        "repeat": "Politely repeat the same question with slightly different wording.",
        "clarify": "Rephrase the same question more clearly for a confused candidate.",
        "redirect": "Politely refocus the candidate on the same question.",
        "simplify": "Simplify the same question for a junior candidate who said they don't know.",
    }.get(mode, "Restate the same question briefly.")

    prompt = f"""
You are a calm technical interviewer on a live voice call.

{mode_instruction}

Hard rules:
- Keep the SAME meaning and domain intent.
- Ask exactly ONE question.
- Do NOT coach, hint at the answer, or give examples of what to say.
- Do NOT stack or repeat the question multiple times.
- Do NOT copy recovery wrappers like "Happy to repeat" or "I'll rephrase" more than once at the start.
- Keep it short and speakable (max 2 short sentences).
- Junior AI Engineer interview tone.

Domain: {domain or "general"}
Canonical question (intent to preserve):
{core}

Return ONLY the spoken line.
""".strip()

    try:
        response = llm_client.chat.completions.create(
            model=llm_model or "llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only the spoken interviewer line. "
                        "One question. No markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=100,
        )
        text = (response.choices[0].message.content or "").strip()
        text = re.sub(r"^[\*\-•\s]+", "", text)
        if text and "?" in text:
            # Guard against accidental multi-ask stacking in the model output.
            from dialogue.guards.echo_guard import canonicalize_for_store

            cleaned = canonicalize_for_store(text)
            if cleaned and cleaned.count("?") <= 2:
                return cleaned if cleaned.endswith("?") or "?" in cleaned else text
            return text
    except Exception as exc:
        logger.warning("Recovery rephrase failed (%s): %s", mode, exc)

    return fallback_recovery_line(mode, core)
