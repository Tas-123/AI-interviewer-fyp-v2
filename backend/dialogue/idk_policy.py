"""
IDK policy — handle "I don't know" without scoring as a technical answer.

Phase 6A: rephrase → hint → skip domain.
"""

from __future__ import annotations

import re

IDK_PHRASES = (
    "i don't know",
    "i dont know",
    "don't know",
    "dont know",
    "no idea",
    "not sure",
    "i'm not sure",
    "im not sure",
    "i have no idea",
    "can't answer",
    "cant answer",
    "don't remember",
    "dont remember",
)

DOMAIN_HINTS: dict[str, str] = {
    "project_overview": (
        "Think of one project — even a small one. What problem did it solve and what did you build?"
    ),
    "python": (
        "Consider folders like src/, a config file, and main.py — how would you lay those out?"
    ),
    "machine_learning": (
        "Compare training accuracy to validation accuracy, and mention regularization or more data."
    ),
    "data_preprocessing": (
        "Missing values can use mean/median imputation; categoricals can use encoding; numerics can be scaled."
    ),
    "model_evaluation": (
        "Accuracy for balance; precision/recall when false positives or false negatives matter; F1 combines both."
    ),
    "nlp_speech_ai": (
        "Think tokenization, normalization, and handling audio or text noise before the model."
    ),
    "apis_backend": (
        "A REST endpoint, request/response JSON schema, and basic error handling."
    ),
    "deployment": (
        "Containerize the model, expose an endpoint, and watch logs plus latency."
    ),
    "debugging_problem_solving": (
        "Check data quality first, then preprocessing, then model outputs step by step."
    ),
    "behavioral_ownership": (
        "Pick a small problem you personally fixed — what you did and what changed."
    ),
}


def is_idk_response(transcript: str) -> bool:
    """True when the candidate signals they cannot answer."""
    text = normalize_idk_text(transcript)
    if not text:
        return False

    cannot_answer_phrases = (
        "don't have answer",
        "dont have answer",
        "don't have an answer",
        "dont have an answer",
        "no answer for this",
        "can't answer this",
        "cant answer this",
        "nothing coming to my mind",
        "nothing comes to my mind",
    )
    if any(phrase in text for phrase in cannot_answer_phrases):
        return True

    if any(phrase in text for phrase in IDK_PHRASES):
        words = text.split()
        if len(words) <= 18:
            return True
        if text.strip() in IDK_PHRASES or text.startswith(("i don't know", "i dont know", "i don't remember", "i dont remember")):
            return True
    return False


def normalize_idk_text(text: str) -> str:
    cleaned = (text or "").lower().strip()
    cleaned = re.sub(r"[^\w\s']", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def idk_attempt_response(
    domain: str,
    attempt: int,
    last_question: str,
) -> tuple[str, str]:
    """
    Return (spoken_response, flow_action) for attempt 1-based count on this domain.
    flow_action: rephrase_idk | hint_idk | skip_domain
    """
    domain = (domain or "").strip().lower()
    last_q = (last_question or "").strip()

    if attempt <= 1:
        return (
            "That's okay — let me ask it a simpler way. "
            f"{_simplify_question(last_q)}",
            "rephrase_idk",
        )

    if attempt == 2:
        hint = DOMAIN_HINTS.get(domain, "Share whatever you remember — even a partial answer helps.")
        return (
            f"No problem. Here's a small hint: {hint} "
            "Please try answering in your own words.",
            "hint_idk",
        )

    return (
        "That's fine — let's move on to a different topic.",
        "skip_domain",
    )


def _simplify_question(question: str) -> str:
    """Shorten/rephrase the last question for a second attempt."""
    from dialogue.guards.echo_guard import canonical_interview_question

    q = canonical_interview_question(question)
    if not q:
        return "Could you walk me through your approach step by step?"
    for label in ("[Follow-up]", "[follow-up]", "Follow-up:", "follow-up:"):
        q = q.replace(label, "")
    q = q.strip()
    if len(q) > 180:
        q = q[:180].rsplit(" ", 1)[0] + "?"
    if not q.endswith("?"):
        q = q.rstrip(".") + "?"
    return q
