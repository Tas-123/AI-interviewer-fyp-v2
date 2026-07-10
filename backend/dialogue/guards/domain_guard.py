"""Domain relevance guard — LLM semantic check with redirect limits."""

from __future__ import annotations

from dialogue.guards.echo_guard import canonical_interview_question
from dialogue.guards.relevance import (
    generate_speakable_redirect,
    is_follow_up_question,
    semantic_answer_relevance,
    should_redirect_for_relevance,
)
from dialogue.guards.types import GuardContext, GuardResult

MAX_DOMAIN_REDIRECTS = 2


def is_answer_relevant_to_question(
    transcript: str,
    last_question: str,
    *,
    llm_client=None,
    llm_model: str = "",
) -> bool:
    """Backward-compatible wrapper — defaults to evaluate when unsure."""
    if is_follow_up_question(last_question):
        return True
    result = semantic_answer_relevance(
        transcript,
        last_question,
        llm_client=llm_client,
        llm_model=llm_model,
    )
    if should_redirect_for_relevance(result):
        return False
    return True


def domain_relevance_redirect_response(
    last_question: str,
    *,
    llm_client=None,
    llm_model: str = "",
    attempt: int = 1,
) -> str:
    """Natural spoken redirect back to the core question."""
    return generate_speakable_redirect(
        last_question,
        llm_client=llm_client,
        llm_model=llm_model,
        attempt=attempt,
    )


class DomainGuard:
    """Redirect only clearly off-topic answers; cap repeats; follow-ups pass."""

    name = "domain"

    def check(self, ctx: GuardContext) -> GuardResult:
        ctx_interview = ctx.interview_context
        canonical_q = canonical_interview_question(ctx.last_question)

        if is_follow_up_question(ctx.last_question):
            return GuardResult(triggered=False)

        redirect_count = 0
        if ctx_interview is not None and hasattr(ctx_interview, "get_domain_redirect_count"):
            redirect_count = ctx_interview.get_domain_redirect_count()

        if redirect_count >= MAX_DOMAIN_REDIRECTS:
            return GuardResult(triggered=False)

        result = semantic_answer_relevance(
            ctx.transcript,
            ctx.last_question,
            llm_client=ctx.llm_client,
            llm_model=ctx.llm_model,
        )

        if not should_redirect_for_relevance(result):
            return GuardResult(triggered=False)

        attempt = redirect_count + 1
        if ctx_interview is not None and hasattr(ctx_interview, "increment_domain_redirect"):
            ctx_interview.increment_domain_redirect()

        return GuardResult(
            triggered=True,
            decision_type="DOMAIN_RELEVANCE_REDIRECT",
            response_text=domain_relevance_redirect_response(
                ctx.last_question,
                llm_client=ctx.llm_client,
                llm_model=ctx.llm_model,
                attempt=attempt,
            ),
            should_evaluate=False,
            metadata={
                "guard": self.name,
                "question": canonical_q,
                "relevance_confidence": result.confidence,
                "relevance_reason": result.reason,
                "redirect_attempt": attempt,
            },
        )
