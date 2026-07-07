"""Ordered guard pipeline executed before adaptive evaluation."""

from __future__ import annotations

from typing import Optional

from dialogue.guards.domain_guard import DomainGuard
from dialogue.guards.echo_guard import EchoGuard
from dialogue.guards.idk_guard import IdkGuard
from dialogue.guards.incomplete_guard import IncompleteGuard
from dialogue.guards.intent_guard import IntentGuard
from dialogue.guards.meta_conversation_guard import MetaConversationGuard
from dialogue.guards.types import Guard, GuardContext, GuardResult


class GuardPipeline:
    """Run pre-evaluation guards in fixed order; stop at first trigger."""

    def __init__(self, guards: Optional[list[Guard]] = None, llm_client=None, llm_model: str = ""):
        if guards is not None:
            self._guards = guards
        else:
            self._guards = [
                EchoGuard(),
                MetaConversationGuard(),
                IdkGuard(),
                IntentGuard(llm_client=llm_client, llm_model=llm_model),
                IncompleteGuard(),
                DomainGuard(),
            ]

    def run(self, ctx: GuardContext) -> Optional[GuardResult]:
        for guard in self._guards:
            result = guard.check(ctx)
            if result.triggered:
                return result
        return None
