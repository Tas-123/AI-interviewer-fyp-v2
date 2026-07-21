"""Hybrid multi-role: predefined templates and bootstrap (no custom specs / PDF)."""

from __future__ import annotations

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("GROQ_API_KEY", "mock-key")

from core.domain_packs import validate_blueprint
from core.interviewer_policy import INTERVIEW_BLUEPRINT
from core.role_registry import get_role_config, list_target_roles
from dialogue.coverage_engine import CoverageEngine
from dialogue.session_bootstrap import bootstrap_from_request, build_candidate_profile


def test_junior_ai_blueprint_unchanged():
    cfg = get_role_config("junior_ai_engineer")
    assert cfg.blueprint == INTERVIEW_BLUEPRINT
    assert len(cfg.blueprint) == 10
    assert cfg.blueprint[0] == "project_overview"
    assert cfg.blueprint[1] == "python"
    assert "python" in cfg.seeds
    assert cfg.seeds["python"]
    engine = CoverageEngine(cfg)
    assert engine.interview_blueprint[0] == "project_overview"
    print("[PASS] test_junior_ai_blueprint_unchanged")


def test_frontend_and_backend_templates_distinct():
    roles = {r["key"] for r in list_target_roles()}
    assert "junior_frontend_developer" in roles
    assert "junior_backend_developer" in roles

    fe = get_role_config("junior_frontend_developer")
    be = get_role_config("junior_backend_developer")
    ai = get_role_config("junior_ai_engineer")

    assert "react_frontend" in fe.blueprint
    assert "html_css" in fe.blueprint
    assert "python" not in fe.blueprint
    assert "databases" in be.blueprint
    assert "auth_security" in be.blueprint
    assert fe.blueprint != ai.blueprint
    assert be.blueprint != ai.blueprint
    assert validate_blueprint(fe.blueprint) == []
    assert validate_blueprint(be.blueprint) == []
    print("[PASS] test_frontend_and_backend_templates_distinct")


def test_bootstrap_frontend_default_profile():
    profile = build_candidate_profile(target_role="junior_frontend_developer")
    assert profile.profile_source == "default"
    assert profile.role == "Junior Frontend Developer"
    assert any("react" in s.lower() or "javascript" in s.lower() for s in profile.skills)
    print("[PASS] test_bootstrap_frontend_default_profile")


def test_bootstrap_skills_from_chips():
    profile = bootstrap_from_request(
        {
            "target_role": "junior_frontend_developer",
            "display_name": "Sam",
            "skills": ["React", "TypeScript"],
            "resume_text": "Built a portfolio site",
        }
    )
    assert profile.name == "Sam"
    assert profile.profile_source == "resume"
    skills_l = [s.lower() for s in profile.skills]
    assert "react" in skills_l or "typescript" in skills_l
    print("[PASS] test_bootstrap_skills_from_chips")


def test_ai_path_without_spec_unchanged():
    profile = bootstrap_from_request({"target_role": "junior_ai_engineer"})
    assert profile.target_role == "junior_ai_engineer"
    assert "Python" in profile.skills or "python" in [s.lower() for s in profile.skills]
    print("[PASS] test_ai_path_without_spec_unchanged")


if __name__ == "__main__":
    tests = [
        test_junior_ai_blueprint_unchanged,
        test_frontend_and_backend_templates_distinct,
        test_bootstrap_frontend_default_profile,
        test_bootstrap_skills_from_chips,
        test_ai_path_without_spec_unchanged,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1

    sys.exit(1 if failed else 0)
