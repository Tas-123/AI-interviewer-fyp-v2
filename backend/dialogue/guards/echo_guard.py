"""Echo guard — detects bot/question repetition in STT output."""

from __future__ import annotations

import re

from dialogue.guards.types import GuardContext, GuardResult


def short_repeat_question(last_question: str = "") -> str:
    """Repeat only the core interview question without long greeting text."""
    q = (last_question or "").strip()
    lq = q.lower()

    if not q:
        return "Please answer the current interview question in your own words."

    intro_markers = [
        "good morning",
        "welcome to the interview",
        "welcome to today's interview",
        "ai engineer position",
        "introducing yourself",
        "introduce yourself",
        "start by introducing yourself",
        "please start by introducing yourself",
        "tell me about a project",
        "tell me about one project",
        "project you've worked on",
        "project you have worked on",
        "showcases your ai",
        "machine learning skills",
        "ai or machine learning",
        "background and experience",
    ]

    if any(m in lq for m in intro_markers):
        return (
            "Please introduce yourself and tell me about one AI or machine "
            "learning project you worked on."
        )

    for prefix in ("[Follow-up]", "[follow-up]", "Follow-up:", "follow-up:"):
        q = q.replace(prefix, "").strip()

    if len(q.split()) > 28 and "?" in q:
        parts = [p.strip() for p in q.split(".") if p.strip()]
        question_parts = [p for p in parts if "?" in p]
        if question_parts:
            q = question_parts[-1].strip()

    return q


def looks_like_bot_question_echo(transcript: str, last_question: str = "") -> bool:
    """Detect when STT captured the interviewer prompt instead of a candidate answer."""
    t = (transcript or "").lower().strip()
    q = (last_question or "").lower().strip()

    if not t:
        return False

    candidate_answer_markers = [
        "i would", "i'd", "i detect", "training loss", "validation loss",
        "overfitting", "regularization", "dropout", "early stopping",
        "fastapi", "docker", "prometheus", "i will", "i used", "i worked",
        "i handled", "i compare", "i usually", "my project", "we used",
        "we built", "we handled", "missing values", "one hot encoding",
        "standard scaling",
    ]
    question_like_markers = [
        "can you", "could you", "please", "tell me about",
        "how would you", "what steps would you", "walk me through",
        "let's talk about", "question is", "answer this question",
    ]

    is_question_like = ("?" in t) or any(m in t for m in question_like_markers)
    has_candidate_answer_marker = any(m in t for m in candidate_answer_markers)

    external_prompt_markers = [
        "answer this question",
        "please answer this question",
        "stay on the current interview question",
        "your last response did not clearly answer",
        "please answer this directly",
        "chatgpt",
        "copy this answer",
        "repeat after me",
        "use this answer",
        "say this answer",
    ]
    if any(p in t for p in external_prompt_markers):
        return True

    echo_phrases = [
        "good morning",
        "welcome to the interview",
        "welcome to today's interview",
        "ai engineer position",
        "introduce yourself",
        "start by introducing yourself",
        "please start by introducing yourself",
        "can you please take a minute to introduce yourself",
        "i'm excited to learn more about your background",
        "tell me about one ai or machine learning project",
        "tell me about a recent ai or machine learning project",
    ]

    if sum(1 for p in echo_phrases if p in t) >= 2:
        return True

    overlap = 0.0
    if q:

        def words(x: str) -> set[str]:
            return set(re.findall(r"[a-zA-Z]{4,}", x))

        tw = words(t)
        qw = words(q)
        if len(tw) >= 6 and len(qw) >= 6:
            overlap = len(tw & qw) / max(1, len(qw))

    if has_candidate_answer_marker:
        return overlap >= 0.85
    if is_question_like and overlap >= 0.85:
        return True
    return False


class EchoGuard:
    """Guard that blocks scoring when the transcript is an echo of the bot question."""

    name = "echo"

    def check(self, ctx: GuardContext) -> GuardResult:
        if not looks_like_bot_question_echo(ctx.transcript, ctx.last_question):
            return GuardResult(triggered=False)

        response = (
            "I detected that the interviewer prompt may have been repeated instead "
            "of a candidate answer. Please answer in your own words. "
            + short_repeat_question(ctx.last_question)
        )
        return GuardResult(
            triggered=True,
            decision_type="BOT_OR_EXTERNAL_PROMPT_ECHO",
            response_text=response,
            should_evaluate=False,
            metadata={"guard": self.name},
        )
