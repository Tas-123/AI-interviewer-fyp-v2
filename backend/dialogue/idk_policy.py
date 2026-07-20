"""
IDK policy — handle "I don't know" without scoring as a technical answer.

Phase 6A: rephrase → hint → skip domain.
UX refinements: broader IDK detection; recoveries use canonical + bounded rephrase.
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
    "i literally don't know",
    "i literally dont know",
    "i didn't done it",
    "i didnt done it",
    "i didn't do it",
    "i didnt do it",
    "i never did",
    "i haven't done",
    "i havent done",
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


def is_hint_request(transcript: str) -> bool:
    """True when the candidate is asking for a hint or help on the question."""
    text = normalize_idk_text(transcript)
    if not text:
        return False

    hint_phrases = (
        "give me a hint",
        "give me hint",
        "any hint",
        "a hint",
        "need a hint",
        "need hint",
        "can you hint",
        "help me",
        "give me help",
        "i don't get it",
        "i dont get it",
        "don't get it",
        "dont get it",
        "i'm stuck",
        "im stuck",
        "not getting it",
        "can you help",
        "please help",
        "hint or anything",
        "hint please",
    )
    if any(p in text for p in hint_phrases):
        return True
    return False


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
        "pass this question",
        "i will pass",
        "i'll pass",
        "ill pass",
        "skip this",
        "i cannot answer",
        "i can't answer",
        "i cant answer",
    )
    if any(phrase in text for phrase in cannot_answer_phrases):
        return True

    if any(phrase in text for phrase in IDK_PHRASES):
        words = text.split()
        # Short IDK utterances always count.
        if len(words) <= 24:
            return True
        # Longer utterances still count when they clearly open with / contain IDK
        # plus refusal to continue (pass / didn't do / no idea).
        if text.startswith(
            (
                "i don't know",
                "i dont know",
                "i don't remember",
                "i dont remember",
                "i have no idea",
                "i'm not sure",
                "im not sure",
            )
        ):
            return True
        refusal_tail = (
            "pass",
            "didn't do",
            "didnt do",
            "never did",
            "no idea",
            "can't answer",
            "cant answer",
        )
        if any(phrase in text for phrase in IDK_PHRASES) and any(
            t in text for t in refusal_tail
        ):
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
    *,
    interview_context=None,
    llm_client=None,
    llm_model: str = "",
) -> tuple[str, str]:
    """
    Return (spoken_response, flow_action) for attempt 1-based count on this domain.
    flow_action: rephrase_idk | hint_idk | skip_domain
    """
    from dialogue.rephrase_policy import rephrase_recovery, resolve_core_question

    domain = (domain or "").strip().lower()
    core = resolve_core_question(interview_context, last_question)

    if attempt <= 1:
        spoken = rephrase_recovery(
            core_question=core,
            domain=domain,
            mode="simplify",
            llm_client=llm_client,
            llm_model=llm_model,
        )
        return spoken, "rephrase_idk"

    if attempt == 2:
        hint = DOMAIN_HINTS.get(
            domain, "Share whatever you remember — even a partial answer helps."
        )
        ask = rephrase_recovery(
            core_question=core,
            domain=domain,
            mode="simplify",
            llm_client=llm_client,
            llm_model=llm_model,
        )
        # Keep hint + one freshly worded ask (no stacked prior TTS).
        return (
            f"No problem. Here's a small hint: {hint} {ask}",
            "hint_idk",
        )

    return (
        "That's okay — we'll continue with another part of the interview.",
        "skip_domain",
    )


def _simplify_question(question: str) -> str:
    """Shorten/rephrase the last question for a second attempt."""
    from dialogue.guards.echo_guard import canonicalize_for_store

    q = canonicalize_for_store(question)
    if not q:
        return "Could you walk me through your approach step by step?"
    if len(q) > 180:
        q = q[:180].rsplit(" ", 1)[0] + "?"
    if not q.endswith("?"):
        q = q.rstrip(".") + "?"
    return q
