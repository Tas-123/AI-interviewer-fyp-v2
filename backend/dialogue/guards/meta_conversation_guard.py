"""
Meta-conversation guard — repeat / already-answered / change-topic without scoring.

Phase 6A: meta utterances must not enter the evaluation pipeline.
"""

from __future__ import annotations

from dialogue.guards.echo_guard import short_repeat_question
from dialogue.guards.types import GuardContext, GuardResult

ALREADY_ANSWERED_PHRASES = (
    "i already answered",
    "i just answered",
    "i just answer you",
    "i just answer",
    "you already asked",
    "i told you already",
    "i said that already",
    "answered that already",
    "i gave you that answer",
)

CHANGE_TOPIC_PHRASES = (
    "change the question",
    "change question",
    "ask something else",
    "different question",
    "another question",
    "can we move on",
    "move on to another",
    "move to the next question",
    "move to next question",
    "go to the next question",
    "go to next question",
    "next question please",
    "can we move to the next",
    "skip this question",
    "skip that question",
    "skip this one",
    "don't have answer",
    "dont have answer",
    "don't have an answer",
    "dont have an answer",
    "no answer for this",
    "can't answer this",
    "cant answer this",
    "don't wanna answer",
    "dont wanna answer",
    "don't want to answer",
    "dont want to answer",
    "i don't wanna answer",
    "i dont wanna answer",
)


def classify_meta_intent(transcript: str) -> str | None:
    """Return meta intent label or None if this is a normal answer attempt."""
    text = (transcript or "").lower().strip()
    if not text:
        return None

    if any(p in text for p in ALREADY_ANSWERED_PHRASES):
        return "ALREADY_ANSWERED"
    if any(p in text for p in CHANGE_TOPIC_PHRASES):
        return "CHANGE_TOPIC"
    return None


def meta_response(intent: str, last_question: str) -> str:
    last_question = (last_question or "").strip()
    repeat_q = short_repeat_question(last_question)

    if intent == "ALREADY_ANSWERED":
        return (
            "Understood — I'll move us forward. "
            "Let's try the next topic."
        )

    if intent == "CHANGE_TOPIC":
        return (
            "Sure — let's switch to a different area of the interview."
        )

    return f"Let's continue. {repeat_q}"


class MetaConversationGuard:
    """Handle meta-conversation without scoring."""

    name = "meta_conversation"

    def check(self, ctx: GuardContext) -> GuardResult:
        intent = classify_meta_intent(ctx.transcript)
        if not intent:
            return GuardResult(triggered=False)

        flow_action = "skip_domain"
        return GuardResult(
            triggered=True,
            decision_type=intent,
            response_text=meta_response(intent, ctx.last_question),
            should_evaluate=False,
            metadata={
                "guard": self.name,
                "intent": intent,
                "flow_action": flow_action,
            },
        )
