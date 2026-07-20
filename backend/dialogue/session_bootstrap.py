"""
Session bootstrap — normalize optional resume input into a CandidateProfile.

Role selects interview structure; resume personalizes intro and question wording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.role_registry import DEFAULT_TARGET_ROLE, RoleConfig, get_role_config
from dialogue.resume_context_parser import (
    generate_resume_questions,
    map_resume_to_domains,
    parse_resume,
)


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
    resume_questions: list = field(default_factory=list)
    resume_by_domain: dict = field(default_factory=dict)

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
            "resume_by_domain": dict(self.resume_by_domain),
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
    projects = list(parsed.get("candidate_projects", []) or [])
    return {
        "skills": skills,
        "tools": list(parsed.get("candidate_tools", [])),
        "experience": experience,
        "detected_role": detected_role,
        "projects": projects,
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
    1. target_role → blueprint + role title (structure)
    2. resume_data / resume_text → skills/tools/projects REPLACE defaults
    3. No resume → copy role default profile (Python/ML fallback)
    """
    role_cfg: RoleConfig = get_role_config(target_role)
    default = dict(role_cfg.default_profile)

    inline_text = (resume_data or {}).get("resume_text") if resume_data else None
    text_to_parse = (resume_text or inline_text or "").strip()
    has_resume = bool(text_to_parse) or _has_substance(resume_data)

    # Bare skeleton — never seed resume path with DEFAULT skills.
    merged: dict[str, Any] = {
        "name": default.get("name", "Candidate"),
        "role": role_cfg.display_title,
        "skills": [],
        "experience": "not specified",
        "projects": [],
        "tools": [],
    }

    profile_source = "default"
    parsed_fields: dict[str, Any] = {}

    if text_to_parse:
        parsed_fields = _parsed_to_fields(parse_resume(text_to_parse))
        profile_source = "resume"

    if _has_substance(resume_data):
        profile_source = "resume"
        rd = resume_data or {}
        if rd.get("name"):
            merged["name"] = str(rd["name"]).strip()
        # Replace (do not merge with defaults) — merge only among resume sources below.
        if rd.get("skills"):
            merged["skills"] = _merge_skills(list(rd["skills"]))
        if rd.get("tools"):
            merged["tools"] = _merge_skills(list(rd["tools"]))
        if rd.get("projects"):
            merged["projects"] = _merge_skills(list(rd["projects"]))
        if rd.get("experience"):
            merged["experience"] = str(rd["experience"]).strip()
        # Explicit resume role is informational only; target_role drives blueprint.
        if rd.get("resume_role"):
            merged["detected_role"] = str(rd["resume_role"]).strip()

    if parsed_fields:
        profile_source = "resume"
        # Merge parsed text with structured resume fields only (never defaults).
        merged["skills"] = _merge_skills(
            merged.get("skills", []),
            parsed_fields.get("skills", []),
        )
        merged["tools"] = _merge_skills(
            merged.get("tools", []),
            parsed_fields.get("tools", []),
        )
        if parsed_fields.get("projects"):
            merged["projects"] = _merge_skills(
                merged.get("projects", []),
                list(parsed_fields["projects"]),
            )
        if parsed_fields.get("experience", "not specified") != "not specified":
            merged["experience"] = parsed_fields["experience"]
        if parsed_fields.get("detected_role", "not specified") != "not specified":
            merged["detected_role"] = parsed_fields["detected_role"]

    if not has_resume or profile_source == "default":
        # No usable resume — fall back to Junior AI default profile.
        profile_source = "default"
        merged["skills"] = list(default.get("skills", []))
        merged["experience"] = default.get("experience", "not specified")
        merged["projects"] = list(default.get("projects", []))
        merged["tools"] = list(default.get("tools", []))
        if not (display_name and display_name.strip()):
            merged["name"] = default.get("name", "Candidate")

    if display_name and display_name.strip():
        merged["name"] = display_name.strip()

    resume_questions: list = []
    resume_by_domain: dict = {}
    if profile_source == "resume":
        parsed_for_questions = {
            "candidate_skills": [s.lower() for s in merged["skills"]],
            "candidate_tools": [t.lower() for t in merged.get("tools", [])],
            "candidate_projects": list(merged.get("projects", [])),
            "candidate_experience": merged.get("experience", "not specified"),
            "candidate_role": merged.get("detected_role", merged["role"]),
        }
        resume_questions = generate_resume_questions(parsed_for_questions)
        resume_by_domain = map_resume_to_domains(
            skills=merged["skills"],
            tools=merged.get("tools", []),
            projects=merged.get("projects", []),
            resume_text=text_to_parse,
        )

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
        resume_by_domain=resume_by_domain,
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
