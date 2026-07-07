"""
Coverage engine — tracks blueprint domain coverage, probes, and advance rules.

Single source of truth for structured interview progression (Phase 3).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from core.role_registry import RoleConfig, get_role_config


class CoverageEngine:
    """Manages domain coverage state for one interview session."""

    def __init__(self, role_config: RoleConfig | None = None):
        cfg = role_config or get_role_config()
        self.target_role = cfg.key
        self.role_title = cfg.display_title
        self.interview_blueprint = list(cfg.blueprint)
        self.max_turns_per_domain = cfg.max_turns_per_domain
        self.max_probes_per_domain = cfg.max_probes_per_domain
        self.max_total_interview_turns = cfg.max_total_interview_turns
        self.max_context_followups_total = cfg.max_context_followups_total

        self.domain_coverage = {domain: 0 for domain in self.interview_blueprint}
        self.domain_probe_counts = {domain: 0 for domain in self.interview_blueprint}
        self.current_domain = self.interview_blueprint[0] if self.interview_blueprint else ""
        self.context_followups_used = 0
        self.context_followup_domains: set[str] = set()

    def get_next_domain(self) -> Optional[str]:
        """Return the next blueprint domain that still needs primary coverage."""
        for domain in self.interview_blueprint:
            if self.domain_coverage.get(domain, 0) < self.max_turns_per_domain:
                return domain
        return None

    def mark_domain_covered(self, domain: str) -> None:
        if not domain:
            return
        if domain not in self.domain_coverage:
            self.domain_coverage[domain] = 0
        self.domain_coverage[domain] += 1

    def set_current_domain(self, domain: str) -> None:
        """Set active domain without incrementing coverage (Phase 6A)."""
        if domain:
            self.current_domain = domain

    def mark_domain_probe(self, domain: str) -> None:
        if not domain:
            return
        if domain not in self.domain_probe_counts:
            self.domain_probe_counts[domain] = 0
        self.domain_probe_counts[domain] += 1

    def can_probe_domain(self, domain: str) -> bool:
        if not domain:
            return False
        return self.domain_probe_counts.get(domain, 0) < self.max_probes_per_domain

    def can_context_followup(self, domain: str) -> bool:
        if not domain:
            return False
        if self.context_followups_used >= self.max_context_followups_total:
            return False
        if domain in self.context_followup_domains:
            return False
        return True

    def mark_context_followup(self, domain: str) -> None:
        if not domain:
            return
        self.context_followups_used += 1
        self.context_followup_domains.add(domain)

    def all_domains_covered(self) -> bool:
        return self.get_next_domain() is None

    def coverage_percent(self) -> float:
        if not self.interview_blueprint:
            return 100.0
        covered = sum(
            1 for domain in self.interview_blueprint
            if self.domain_coverage.get(domain, 0) >= self.max_turns_per_domain
        )
        return round(100.0 * covered / len(self.interview_blueprint), 1)

    def get_summary(self) -> dict:
        return {
            "target_role": self.target_role,
            "role_title": self.role_title,
            "blueprint": list(self.interview_blueprint),
            "coverage": deepcopy(self.domain_coverage),
            "probe_counts": deepcopy(self.domain_probe_counts),
            "current_domain": self.current_domain,
            "coverage_percent": self.coverage_percent(),
            "all_domains_covered": self.all_domains_covered(),
            "max_turns_per_domain": self.max_turns_per_domain,
            "max_probes_per_domain": self.max_probes_per_domain,
            "max_total_interview_turns": self.max_total_interview_turns,
            "context_followups_used": self.context_followups_used,
        }
