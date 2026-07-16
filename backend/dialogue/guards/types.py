"""Guard pipeline types and contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class GuardContext:
    """Input passed to each pre-evaluation guard."""

    transcript: str
    last_question: str
    interview_context: Any = None
    llm_client: Any = None
    llm_model: str = ""
    transcript_quality: dict | None = None


@dataclass
class GuardResult:
    """Output when a guard blocks evaluation."""

    triggered: bool = False
    decision_type: str = ""
    response_text: Optional[str] = None
    should_evaluate: bool = True
    metadata: dict = field(default_factory=dict)


class Guard(Protocol):
    """Protocol for composable pre-evaluation guards."""

    name: str

    def check(self, ctx: GuardContext) -> GuardResult:
        ...
