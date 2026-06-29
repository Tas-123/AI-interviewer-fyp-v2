"""
Session bootstrap — normalize optional resume input into a CandidateProfile.

Role selects interview structure; resume personalizes intro and question wording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.role_registry import DEFAULT_TARGET_ROLE, RoleConfig, get_role_config
from dialogue.resume_context_parser import generate_resume_questions, parse_resume


@dataclass
class CandidateProfile:
    """Normalized candidate profile consumed by InterviewContext / SessionService."""

    name: str
    role: str
    skills: list[str]
    experience: str
    projects: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    target_role: str = DEFAULT_TARGET_ROLE
    profile_source: str = "default"  # "resume" | "default"
    resume_questions: list[str] = field(default_factory=list)

    def to_resume_data(self) -> dict[str, Any]:
        """Dict passed to DialogueManager and persisted to DB."""
        return {
            "name": self.name,
            "role": self.role,
            "skills": list(self.skills),
            "experience": self.experience,
            "projects": list(self.projects),
            "tools": list(self.tools),
            "target_role": self.target_role,
            "profile_source": self.profile_source,
            "_resume_questions": list(self.resume_questions),
        }

    def to_metadata(self) -> dict[str, Any]:
        """Lightweight metadata for reports and API responses."""
        return {
            "name": self.name,
            "role": self.role,
            "target_role": self.target_role,
            "profile_source": self.profile_source,
            "skills_count": len(self.skills),
            "resume_questions_count": len(self.resume_questions),
        }


def _has_substance(resume_data: dict | None) -> bool:
    if not resume_data or not isinstance(resume_data, dict):
        return False
    for key in ("skills", "experience", "projects", "tools", "resume_text"):
        value = resume_data.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and value:
            return True
    if resume_data.get("name") and str(resume_data.get("name")).strip().lower() != "candidate":
        return True
    return False


def _merge_skills(*sources: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for source in sources:
        for item in source or []:
            text = str(item).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
    return merged


def _parsed_to_fields(parsed: dict) -> dict[str, Any]:
    """Map resume_context_parser output to resume_data field names."""
    skills = _merge_skills(
        parsed.get("candidate_skills", []),
        parsed.get("candidate_tools", []),
    )
    experience = parsed.get("candidate_experience", "not specified")
    detected_role = parsed.get("candidate_role", "not specified")
    return {
        "skills": skills,
        "tools": list(parsed.get("candidate_tools", [])),
        "experience": experience,
        "detected_role": detected_role,
    }


def build_candidate_profile(
    *,
    target_role: str | None = None,
    resume_data: dict | None = None,
    resume_text: str | None = None,
    display_name: str | None = None,
) -> CandidateProfile:
    """
    Build a normalized candidate profile for session start.

    Priority:
    1. target_role → blueprint + default profile (structure)
    2. resume_data / resume_text → personalization overlay (wording)
    """
    role_cfg: RoleConfig = get_role_config(target_role)
    default = dict(role_cfg.default_profile)

    merged: dict[str, Any] = {
        "name": default.get("name", "Candidate"),
        "role": role_cfg.display_title,
        "skills": list(default.get("skills", [])),
        "experience": default.get("experience", "not specified"),
        "projects": list(default.get("projects", [])),
        "tools": list(default.get("tools", [])),
    }

    profile_source = "default"
    parsed_fields: dict[str, Any] = {}

    inline_text = (resume_data or {}).get("resume_text") if resume_data else None
    text_to_parse = (resume_text or inline_text or "").strip()

    if text_to_parse:
        parsed_fields = _parsed_to_fields(parse_resume(text_to_parse))
        profile_source = "resume"

    if _has_substance(resume_data):
        profile_source = "resume"
        rd = resume_data or {}
        if rd.get("name"):
            merged["name"] = str(rd["name"]).strip()
        if rd.get("skills"):
            merged["skills"] = _merge_skills(merged["skills"], list(rd["skills"]))
        if rd.get("tools"):
            merged["tools"] = _merge_skills(merged["tools"], list(rd["tools"]))
        if rd.get("projects"):
            merged["projects"] = _merge_skills(merged["projects"], list(rd["projects"]))
        if rd.get("experience"):
            merged["experience"] = str(rd["experience"]).strip()
        # Explicit resume role is informational only; target_role drives blueprint.
        if rd.get("resume_role"):
            merged["detected_role"] = str(rd["resume_role"]).strip()

    if parsed_fields:
        merged["skills"] = _merge_skills(merged["skills"], parsed_fields.get("skills", []))
        merged["tools"] = _merge_skills(merged["tools"], parsed_fields.get("tools", []))
        if parsed_fields.get("experience", "not specified") != "not specified":
            merged["experience"] = parsed_fields["experience"]
        if parsed_fields.get("detected_role", "not specified") != "not specified":
            merged["detected_role"] = parsed_fields["detected_role"]

    if display_name and display_name.strip():
        merged["name"] = display_name.strip()

    resume_questions: list[str] = []
    if profile_source == "resume":
        parsed_for_questions = {
            "candidate_skills": [s.lower() for s in merged["skills"]],
            "candidate_tools": [t.lower() for t in merged.get("tools", [])],
            "candidate_experience": merged.get("experience", "not specified"),
            "candidate_role": merged.get("detected_role", merged["role"]),
        }
        resume_questions = generate_resume_questions(parsed_for_questions)

    return CandidateProfile(
        name=merged["name"],
        role=role_cfg.display_title,
        skills=merged["skills"],
        experience=merged["experience"],
        projects=list(merged.get("projects", [])),
        tools=list(merged.get("tools", [])),
        target_role=role_cfg.key,
        profile_source=profile_source,
        resume_questions=resume_questions,
    )


def bootstrap_from_request(payload: dict | None = None) -> CandidateProfile:
    """
    Accept flexible session-start payloads from REST, Pipecat, or dev WS.

    Supported keys: target_role, resume_data, resume_text, display_name,
    plus legacy flat resume fields at the top level.
    """
    payload = payload or {}

    nested = payload.get("resume_data")
    if isinstance(nested, dict):
        resume_data = dict(nested)
    else:
        resume_data = {}
        for key in ("skills", "experience", "projects", "tools", "name", "resume_text", "resume_role"):
            if key in payload:
                resume_data[key] = payload[key]

    return build_candidate_profile(
        target_role=payload.get("target_role"),
        resume_data=resume_data if resume_data else None,
        resume_text=payload.get("resume_text"),
        display_name=payload.get("display_name"),
    )
