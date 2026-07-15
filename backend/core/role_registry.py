"""
Role registry — maps target roles to interview blueprints and default profiles.

Phase 3: target_role selects structure; resume personalizes wording within that role.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.interviewer_policy import (
    DEFAULT_CANDIDATE_PROFILE,
    INTERVIEW_BLUEPRINT,
    MAX_CONTEXT_FOLLOWUPS_TOTAL,
    MAX_PROBES_PER_DOMAIN,
    MAX_SKIPS_PER_INTERVIEW,
    MAX_TOTAL_INTERVIEW_TURNS,
    MAX_TURNS_PER_DOMAIN,
)

DEFAULT_TARGET_ROLE = "junior_ai_engineer"


@dataclass(frozen=True)
class RoleConfig:
    """Configuration for one interview target role."""

    key: str
    display_title: str
    blueprint: tuple[str, ...]
    default_profile: dict[str, Any]
    max_turns_per_domain: int = MAX_TURNS_PER_DOMAIN
    max_probes_per_domain: int = MAX_PROBES_PER_DOMAIN
    max_total_interview_turns: int = MAX_TOTAL_INTERVIEW_TURNS
    max_context_followups_total: int = MAX_CONTEXT_FOLLOWUPS_TOTAL
    max_skips_per_interview: int = MAX_SKIPS_PER_INTERVIEW


ROLE_REGISTRY: dict[str, RoleConfig] = {
    "junior_ai_engineer": RoleConfig(
        key="junior_ai_engineer",
        display_title="Junior AI Engineer",
        blueprint=INTERVIEW_BLUEPRINT,
        default_profile=dict(DEFAULT_CANDIDATE_PROFILE),
    ),
}


def get_role_config(target_role: str | None = None) -> RoleConfig:
    """Return role config; unknown keys fall back to Junior AI Engineer."""
    key = (target_role or DEFAULT_TARGET_ROLE).strip().lower()
    return ROLE_REGISTRY.get(key, ROLE_REGISTRY[DEFAULT_TARGET_ROLE])


def list_target_roles() -> list[dict[str, str]]:
    """Return available target roles for API/client UIs."""
    return [
        {"key": cfg.key, "display_title": cfg.display_title}
        for cfg in ROLE_REGISTRY.values()
    ]
