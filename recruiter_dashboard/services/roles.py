"""
Static role list for the Recruiter dropdown.

Kept local (not imported from backend) so the recruiter module stays
independent of the interview engine. Keep in sync with
backend/core/role_registry.py when new roles are added.
"""

from __future__ import annotations

DEFAULT_TARGET_ROLE = "junior_ai_engineer"

ROLE_OPTIONS: list[dict[str, str]] = [
    {
        "key": "junior_ai_engineer",
        "display_title": "Junior AI Engineer",
    },
]


def list_roles() -> list[dict[str, str]]:
    return list(ROLE_OPTIONS)


def is_known_role(target_role: str) -> bool:
    key = (target_role or "").strip().lower()
    return any(r["key"] == key for r in ROLE_OPTIONS)


def normalize_role(target_role: str | None) -> str:
    key = (target_role or DEFAULT_TARGET_ROLE).strip().lower()
    if is_known_role(key):
        return key
    return DEFAULT_TARGET_ROLE
