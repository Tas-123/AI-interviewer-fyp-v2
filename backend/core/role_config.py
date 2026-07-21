"""RoleConfig dataclass — shared contract for templates and InterviewSpec compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.interviewer_policy import (
    MAX_CONTEXT_FOLLOWUPS_TOTAL,
    MAX_PROBES_PER_DOMAIN,
    MAX_SKIPS_PER_INTERVIEW,
    MAX_TOTAL_INTERVIEW_TURNS,
    MAX_TURNS_PER_DOMAIN,
)


@dataclass(frozen=True)
class RoleConfig:
    """Configuration for one interview target role or compiled custom spec."""

    key: str
    display_title: str
    blueprint: tuple[str, ...]
    default_profile: dict[str, Any]
    max_turns_per_domain: int = MAX_TURNS_PER_DOMAIN
    max_probes_per_domain: int = MAX_PROBES_PER_DOMAIN
    max_total_interview_turns: int = MAX_TOTAL_INTERVIEW_TURNS
    max_context_followups_total: int = MAX_CONTEXT_FOLLOWUPS_TOTAL
    max_skips_per_interview: int = MAX_SKIPS_PER_INTERVIEW
    seeds: dict[str, str] = field(default_factory=dict)
    spoken_cores: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    hints: dict[str, str] = field(default_factory=dict)
    technical_domains: tuple[str, ...] = ()
    high_value_domains: tuple[str, ...] = ()
    skill_domain_map: dict[str, str] = field(default_factory=dict)
    keyword_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    interview_spec_id: str | None = None
    source: str = "template"  # "template" | "custom_spec"
