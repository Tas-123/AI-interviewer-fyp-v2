"""
Role registry — maps predefined target roles to RoleConfig.
"""

from __future__ import annotations

from core.role_config import RoleConfig

# Re-export for existing imports: `from core.role_registry import RoleConfig`
__all__ = [
    "DEFAULT_TARGET_ROLE",
    "ROLE_REGISTRY",
    "RoleConfig",
    "get_role_config",
    "list_target_roles",
    "resolve_role_config",
]

DEFAULT_TARGET_ROLE = "junior_ai_engineer"


def _build_registry() -> dict[str, RoleConfig]:
    from core.role_templates import (
        build_junior_ai_engineer,
        build_junior_backend_developer,
        build_junior_frontend_developer,
    )

    configs = (
        build_junior_ai_engineer(),
        build_junior_frontend_developer(),
        build_junior_backend_developer(),
    )
    return {cfg.key: cfg for cfg in configs}


ROLE_REGISTRY: dict[str, RoleConfig] = _build_registry()


def get_role_config(target_role: str | None = None) -> RoleConfig:
    """Return role config; unknown keys fall back to Junior AI Engineer."""
    key = (target_role or DEFAULT_TARGET_ROLE).strip().lower()
    return ROLE_REGISTRY.get(key, ROLE_REGISTRY[DEFAULT_TARGET_ROLE])


def resolve_role_config(
    *,
    target_role: str | None = None,
    interview_spec_id: str | None = None,
) -> RoleConfig:
    """Resolve RoleConfig from a curated template (interview_spec_id ignored)."""
    return get_role_config(target_role)


def list_target_roles() -> list[dict[str, str]]:
    """Return available target roles for API/client UIs."""
    return [
        {"key": cfg.key, "display_title": cfg.display_title}
        for cfg in ROLE_REGISTRY.values()
    ]
