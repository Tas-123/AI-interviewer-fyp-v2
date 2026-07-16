"""
IDK guard — route "I don't know" through rephrase / hint / skip without scoring.
"""

from __future__ import annotations

from dialogue.idk_policy import idk_attempt_response, is_idk_response
from dialogue.guards.types import GuardContext, GuardResult


class IdkGuard:
    """Intercept honest IDK responses before adaptive evaluation."""

    name = "idk"

    def check(self, ctx: GuardContext) -> GuardResult:
        if not is_idk_response(ctx.transcript):
            return GuardResult(triggered=False)

        interview_ctx = ctx.interview_context
        domain = getattr(interview_ctx, "current_domain", "") if interview_ctx else ""

        attempt = 1
        if interview_ctx and hasattr(interview_ctx, "record_idk_attempt"):
            attempt = interview_ctx.record_idk_attempt(domain)

        response, flow_action = idk_attempt_response(
            domain,
            attempt,
            ctx.last_question,
            interview_context=interview_ctx,
            llm_client=ctx.llm_client,
            llm_model=ctx.llm_model,
        )

        return GuardResult(
            triggered=True,
            decision_type="IDK_RESPONSE",
            response_text=response,
            should_evaluate=False,
            metadata={
                "guard": self.name,
                "flow_action": flow_action,
                "domain": domain,
                "idk_attempt": attempt,
            },
        )
