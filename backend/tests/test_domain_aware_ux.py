"""Domain-aware UX: role-parameterized intro prompts and invite resolve payload."""

from __future__ import annotations

import os
import sys
import types

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

recruiter_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "recruiter_dashboard")
)
if recruiter_dir not in sys.path:
    sys.path.insert(0, recruiter_dir)

os.environ.setdefault("GROQ_API_KEY", "mock-key")

from dialogue.llm_adapter import resolve_role_title
from dialogue.prompts import INTRO_SYSTEM_PROMPT, INTERVIEWER_PERSONA_SYSTEM_PROMPT
from services.roles import get_role_meta, list_roles


def test_intro_prompt_uses_role_title_not_hardcoded_ai():
    fe = INTRO_SYSTEM_PROMPT.format(
        role_title="Junior Frontend Developer",
        skills="React, TypeScript",
        experience="1 year",
    )
    assert "Junior Frontend Developer" in fe
    assert "Junior AI Engineer" not in fe
    assert "{role_title}" not in fe
    assert "React, TypeScript" in fe

    ai = INTRO_SYSTEM_PROMPT.format(
        role_title="Junior AI Engineer",
        skills="Python, Machine Learning",
        experience="not specified",
    )
    assert "Junior AI Engineer" in ai

    persona = INTERVIEWER_PERSONA_SYSTEM_PROMPT.format(role_title="Junior Backend Developer")
    assert "Junior Backend Developer" in persona
    assert "Junior AI Engineer" not in persona
    print("[PASS] test_intro_prompt_uses_role_title_not_hardcoded_ai")


def test_resolve_role_title_prefers_resume_then_config():
    ctx = types.SimpleNamespace(
        resume_data={"role": "Junior Frontend Developer"},
        role_config=types.SimpleNamespace(display_title="Junior AI Engineer"),
    )
    assert resolve_role_title(ctx) == "Junior Frontend Developer"

    ctx2 = types.SimpleNamespace(
        resume_data={},
        role_config=types.SimpleNamespace(display_title="Junior Backend Developer"),
    )
    assert resolve_role_title(ctx2) == "Junior Backend Developer"

    assert resolve_role_title(None) == "technical interview"
    assert resolve_role_title(types.SimpleNamespace(resume_data={}, role_config=None)) == (
        "technical interview"
    )
    print("[PASS] test_resolve_role_title_prefers_resume_then_config")


def test_role_catalog_includes_display_title_and_skills():
    roles = list_roles()
    keys = {r["key"] for r in roles}
    assert "junior_frontend_developer" in keys
    fe = get_role_meta("junior_frontend_developer")
    assert fe["display_title"] == "Junior Frontend Developer"
    assert "React" in fe["suggested_skills"]
    assert "description" in fe and "Frontend" in fe["description"]
    print("[PASS] test_role_catalog_includes_display_title_and_skills")


def test_invite_resolve_payload_shape():
    from api.invites import _public_invite_payload

    invite = {
        "invite_token": "tok_test",
        "target_role": "junior_frontend_developer",
        "label": "July cohort",
        "status": "pending",
        "session_id": None,
        "display_title": "Junior Frontend Developer",
        "description": "A real-time voice interview for Junior Frontend Developer candidates.",
        "suggested_skills": ["HTML", "CSS", "React"],
    }
    payload = _public_invite_payload(invite)
    assert payload["display_title"] == "Junior Frontend Developer"
    assert payload["suggested_skills"] == ["HTML", "CSS", "React"]
    assert "Frontend" in (payload.get("description") or "")
    assert payload["target_role"] == "junior_frontend_developer"
    assert "interview_spec_id" not in payload
    print("[PASS] test_invite_resolve_payload_shape")


def test_invite_resolve_falls_back_to_role_meta():
    from api.invites import _public_invite_payload

    bare = {
        "invite_token": "tok_bare",
        "target_role": "junior_backend_developer",
        "label": None,
        "status": "pending",
        "session_id": None,
    }
    payload = _public_invite_payload(bare)
    assert payload["display_title"] == "Junior Backend Developer"
    assert "FastAPI" in payload["suggested_skills"] or "SQL" in payload["suggested_skills"]
    assert payload["description"]
    print("[PASS] test_invite_resolve_falls_back_to_role_meta")


if __name__ == "__main__":
    tests = [
        test_intro_prompt_uses_role_title_not_hardcoded_ai,
        test_resolve_role_title_prefers_resume_then_config,
        test_role_catalog_includes_display_title_and_skills,
        test_invite_resolve_payload_shape,
        test_invite_resolve_falls_back_to_role_meta,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1
    sys.exit(1 if failed else 0)
