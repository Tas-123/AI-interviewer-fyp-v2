"""
Phase 3 tests — session bootstrap, coverage engine, optional resume flow.
"""

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("GROQ_API_KEY", "mock-key")

from dialogue.session_bootstrap import build_candidate_profile, bootstrap_from_request
from dialogue.coverage_engine import CoverageEngine
from core.role_registry import DEFAULT_TARGET_ROLE, get_role_config


def test_default_profile_no_resume():
    profile = build_candidate_profile()
    assert profile.profile_source == "default"
    assert profile.target_role == DEFAULT_TARGET_ROLE
    assert profile.role == "Junior AI Engineer"
    assert len(profile.skills) >= 5
    assert profile.resume_questions == []
    data = profile.to_resume_data()
    assert data["profile_source"] == "default"
    print("[PASS] test_default_profile_no_resume")


def test_resume_text_personalization():
    text = """
    John Doe — ML Engineer
    3 years experience with Python, TensorFlow, PyTorch, NLP, and FastAPI.
    Built a speech recognition pipeline using deep learning.
    """
    profile = build_candidate_profile(
        resume_text=text,
        display_name="John",
    )
    assert profile.profile_source == "resume"
    assert profile.name == "John"
    assert "python" in [s.lower() for s in profile.skills]
    assert len(profile.resume_questions) > 0
    print("[PASS] test_resume_text_personalization")


def test_resume_data_structured():
    profile = build_candidate_profile(
        resume_data={
            "skills": ["Python", "Docker"],
            "experience": "2 years",
            "name": "Sam",
        }
    )
    assert profile.profile_source == "resume"
    assert "Docker" in profile.skills
    assert profile.experience == "2 years"
    print("[PASS] test_resume_data_structured")


def test_resume_skills_replace_defaults_not_merge():
    """Resume skills replace defaults — no Python/ML pollution when absent."""
    profile = build_candidate_profile(
        resume_text=(
            "Aisha Khan — AI Researcher\n"
            "Focus areas: NLP, Computer Vision, YOLO for object detection.\n"
            "Built a document classification and CV pipeline."
        )
    )
    assert profile.profile_source == "resume"
    skills_l = [s.lower() for s in profile.skills]
    assert any("nlp" in s for s in skills_l) or any("vision" in s for s in skills_l)
    # Default-only skills must not appear unless present in the resume text.
    assert "python" not in skills_l
    assert "machine learning" not in skills_l
    assert "data preprocessing" not in skills_l
    assert "model evaluation" not in skills_l
    print("[PASS] test_resume_skills_replace_defaults_not_merge")


def test_resume_structured_skills_not_merged_with_defaults():
    profile = build_candidate_profile(resume_data={"skills": ["Docker"]})
    assert profile.profile_source == "resume"
    assert profile.skills == ["Docker"]
    print("[PASS] test_resume_structured_skills_not_merged_with_defaults")


def test_empty_resume_falls_back_to_default():
    profile = build_candidate_profile(resume_data={})
    assert profile.profile_source == "default"
    print("[PASS] test_empty_resume_falls_back_to_default")


def test_target_role_wins_for_blueprint():
    profile = build_candidate_profile(
        target_role="junior_ai_engineer",
        resume_text="Frontend developer with React and Vue",
    )
    assert profile.role == "Junior AI Engineer"
    cfg = get_role_config(profile.target_role)
    engine = CoverageEngine(cfg)
    assert len(engine.interview_blueprint) == 10
    assert engine.interview_blueprint[0] == "project_overview"
    print("[PASS] test_target_role_wins_for_blueprint")


def test_bootstrap_from_request_payload():
    profile = bootstrap_from_request({
        "target_role": "junior_ai_engineer",
        "resume_data": {"skills": ["Python"]},
        "display_name": "Test User",
    })
    assert profile.name == "Test User"
    assert profile.profile_source == "resume"
    print("[PASS] test_bootstrap_from_request_payload")


def test_coverage_engine_advance():
    engine = CoverageEngine(get_role_config())
    first = engine.get_next_domain()
    assert first == "project_overview"
    engine.mark_domain_covered(first)
    second = engine.get_next_domain()
    assert second == "python"
    assert engine.coverage_percent() > 0
    print("[PASS] test_coverage_engine_advance")


def test_phase3_templates_in_registry():
    from core.role_registry import list_target_roles

    keys = {r["key"] for r in list_target_roles()}
    assert "junior_ai_engineer" in keys
    assert "junior_frontend_developer" in keys
    assert "junior_backend_developer" in keys
    fe = build_candidate_profile(target_role="junior_frontend_developer")
    assert fe.role == "Junior Frontend Developer"
    print("[PASS] test_phase3_templates_in_registry")


def test_coverage_probe_limits():
    engine = CoverageEngine(get_role_config())
    domain = "python"
    assert engine.can_probe_domain(domain)
    engine.mark_domain_probe(domain)
    assert not engine.can_probe_domain(domain)
    print("[PASS] test_coverage_probe_limits")


if __name__ == "__main__":
    tests = [
        test_default_profile_no_resume,
        test_resume_text_personalization,
        test_resume_data_structured,
        test_resume_skills_replace_defaults_not_merge,
        test_resume_structured_skills_not_merged_with_defaults,
        test_empty_resume_falls_back_to_default,
        test_target_role_wins_for_blueprint,
        test_bootstrap_from_request_payload,
        test_coverage_engine_advance,
        test_phase3_templates_in_registry,
        test_coverage_probe_limits,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1
    sys.exit(1 if failed else 0)
