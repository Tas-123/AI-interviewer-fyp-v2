"""
Meta-conversation guard — skip / already-answered / change-topic without scoring.
"""

from __future__ import annotations

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

# Explicit skip / change topic (consumes skip budget).
HARD_SKIP_PHRASES = (
    "change the question",
    "ask something else",
    "different question",
    "skip this question",
    "skip this one",
    "don't have an answer",
    "dont have an answer",
    "still don't get it",
    "still dont get it",
    "let's move on",
    "lets move on",
    "move on please",
)

# Soft advance — stay on current question (does not skip).
SOFT_ADVANCE_PHRASES = (
    "move to the next question",
    "move to next question",
    "go to the next question",
    "next question please",
    "can we move to the next",
    "next question",
)

PREVIOUS_QUESTION_PHRASES = (
    "previous question",
    "ask the previous",
    "go back to the previous",
    "ask previous question",
    "last question again",
    "the question before",
)


def classify_meta_intent(transcript: str) -> str | None:
    """Fast phrase match for obvious meta requests."""
    text = (transcript or "").lower().strip()
    if not text:
        return None

    if any(p in text for p in PREVIOUS_QUESTION_PHRASES):
        return "PREVIOUS_QUESTION"
    if any(p in text for p in ALREADY_ANSWERED_PHRASES):
        return "ALREADY_ANSWERED"
    if any(p in text for p in HARD_SKIP_PHRASES):
        return "CHANGE_TOPIC"
    if any(p in text for p in SOFT_ADVANCE_PHRASES):
        return "STAY_ON_QUESTION"
    return None


def looks_like_meta_utterance(transcript: str) -> bool:
    text = (transcript or "").lower()
    markers = (
        "next question", "move on", "skip", "same question", "again",
        "don't understand", "dont understand", "already answered",
        "change topic", "something else", "previous question",
    )
    return any(m in text for m in markers)


def meta_response(
    intent: str,
    last_question: str,
    *,
    interview_context=None,
    llm_client=None,
    llm_model: str = "",
) -> str:
    from dialogue.rephrase_policy import rephrase_recovery, resolve_core_question

    if intent == "ALREADY_ANSWERED":
        return "Understood — I've noted that. We'll continue from here."

    if intent == "CHANGE_TOPIC":
        return "Sure — we can cover a different area next."

    core = resolve_core_question(interview_context, last_question)
    domain = ""
    if interview_context is not None:
        domain = str(getattr(interview_context, "current_domain", "") or "")
    return rephrase_recovery(
        core_question=core,
        domain=domain,
        mode="redirect",
        llm_client=llm_client,
        llm_model=llm_model,
    )


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

        if intent in ("STAY_ON_QUESTION", "PREVIOUS_QUESTION"):
            flow_action = "stay_on_question"
        else:
            flow_action = "skip_domain"

        return GuardResult(
            triggered=True,
            decision_type=intent,
            response_text=meta_response(
                intent,
                ctx.last_question,
                interview_context=ctx.interview_context,
                llm_client=ctx.llm_client,
                llm_model=ctx.llm_model,
            ),
            should_evaluate=False,
            metadata={
                "guard": self.name,
                "intent": intent,
                "flow_action": flow_action,
            },
        )
