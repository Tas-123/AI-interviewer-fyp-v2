"""
Meta-conversation guard — skip / already-answered / change-topic without scoring.
"""

from __future__ import annotations

from dialogue.guards.echo_guard import short_repeat_question
from dialogue.guards.intent_guard import semantic_meta_intent_classify
from dialogue.guards.types import GuardContext, GuardResult

ALREADY_ANSWERED_PHRASES = (
    "i already answered",
    "i just answered",
    "i just answer you",
    "you already asked",
    "you asked me",
    "same question",
    "third time",
    "again and again",
    "i told you already",
    "i said that already",
)

CHANGE_TOPIC_PHRASES = (
    "change the question",
    "ask something else",
    "different question",
    "move to the next question",
    "move to next question",
    "go to the next question",
    "next question please",
    "can we move to the next",
    "skip this question",
    "let's move on",
    "lets move on",
    "move on please",
    "don't have an answer",
    "dont have an answer",
    "still don't get it",
    "still dont get it",
)


def classify_meta_intent(transcript: str) -> str | None:
    """Fast phrase match for obvious meta requests."""
    text = (transcript or "").lower().strip()
    if not text:
        return None

    if any(p in text for p in ALREADY_ANSWERED_PHRASES):
        return "ALREADY_ANSWERED"
    if any(p in text for p in CHANGE_TOPIC_PHRASES):
        return "CHANGE_TOPIC"
    return None


def looks_like_meta_utterance(transcript: str) -> bool:
    text = (transcript or "").lower()
    markers = (
        "next question", "move on", "skip", "same question", "again",
        "don't understand", "dont understand", "already answered",
        "change topic", "something else",
    )
    return any(m in text for m in markers)


def meta_response(intent: str, last_question: str) -> str:
    last_question = (last_question or "").strip()

    if intent == "ALREADY_ANSWERED":
        return "Understood — I'll move us forward. Let's try the next topic."

    if intent == "CHANGE_TOPIC":
        return "Sure — let's switch to a different area of the interview."

    return f"Let's continue. {short_repeat_question(last_question)}"


class MetaConversationGuard:
    """Handle meta-conversation without scoring."""

    name = "meta_conversation"

    def check(self, ctx: GuardContext) -> GuardResult:
        intent = classify_meta_intent(ctx.transcript)

        if not intent and looks_like_meta_utterance(ctx.transcript):
            intent = semantic_meta_intent_classify(
                ctx.transcript,
                ctx.last_question,
                llm_client=ctx.llm_client,
                llm_model=ctx.llm_model,
            )

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
