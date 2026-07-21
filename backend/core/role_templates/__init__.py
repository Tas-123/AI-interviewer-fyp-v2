"""Curated RoleConfig builders for registered interview templates."""

from __future__ import annotations

from core.role_config import RoleConfig
from core.interviewer_policy import (
    DEFAULT_CANDIDATE_PROFILE,
    MAX_CONTEXT_FOLLOWUPS_TOTAL,
    MAX_PROBES_PER_DOMAIN,
    MAX_SKIPS_PER_INTERVIEW,
    MAX_TOTAL_INTERVIEW_TURNS,
    MAX_TURNS_PER_DOMAIN,
)
from core.domain_packs import (
    AI_API_SEED,
    AI_DEBUG_SEED,
    AI_DEPLOY_SEED,
    AI_PROJECT_OVERVIEW_CORE,
    AI_PROJECT_OVERVIEW_SEED,
    high_value_domains_for,
    hints_for,
    keyword_map_for,
    labels_for,
    seeds_for,
    skill_domain_map_for,
    spoken_cores_for,
    technical_domains_for,
)

JUNIOR_AI_BLUEPRINT: tuple[str, ...] = (
    "project_overview",
    "python",
    "machine_learning",
    "data_preprocessing",
    "model_evaluation",
    "nlp_speech_ai",
    "apis_backend",
    "deployment",
    "debugging_problem_solving",
    "behavioral_ownership",
)

JUNIOR_FRONTEND_BLUEPRINT: tuple[str, ...] = (
    "project_overview",
    "html_css",
    "javascript",
    "react_frontend",
    "frontend_apis",
    "debugging_problem_solving",
    "behavioral_ownership",
)

JUNIOR_BACKEND_BLUEPRINT: tuple[str, ...] = (
    "project_overview",
    "backend_language",
    "apis_backend",
    "databases",
    "auth_security",
    "deployment",
    "debugging_problem_solving",
    "behavioral_ownership",
)

FRONTEND_DEFAULT_PROFILE: dict = {
    "name": "Candidate",
    "role": "Junior Frontend Developer",
    "skills": [
        "HTML",
        "CSS",
        "JavaScript",
        "React",
        "REST APIs",
    ],
    "experience": (
        "Entry-level to junior frontend developer with project experience in "
        "HTML, CSS, JavaScript, React, and API integration."
    ),
}

BACKEND_DEFAULT_PROFILE: dict = {
    "name": "Candidate",
    "role": "Junior Backend Developer",
    "skills": [
        "Python",
        "REST APIs",
        "SQL",
        "Docker",
        "Authentication",
    ],
    "experience": (
        "Entry-level to junior backend developer with project experience in "
        "APIs, databases, auth, and deployment."
    ),
}


def _pack_fields(blueprint: tuple[str, ...], *, seed_overrides: dict[str, str] | None = None,
                 core_overrides: dict[str, str] | None = None) -> dict:
    return {
        "seeds": seeds_for(blueprint, overrides=seed_overrides),
        "spoken_cores": spoken_cores_for(blueprint, overrides=core_overrides),
        "labels": labels_for(blueprint),
        "hints": hints_for(blueprint),
        "technical_domains": technical_domains_for(blueprint),
        "high_value_domains": high_value_domains_for(blueprint),
        "skill_domain_map": skill_domain_map_for(blueprint),
        "keyword_map": keyword_map_for(blueprint),
    }


def build_junior_ai_engineer() -> RoleConfig:
    seed_overrides = {
        "project_overview": AI_PROJECT_OVERVIEW_SEED,
        "apis_backend": AI_API_SEED,
        "deployment": AI_DEPLOY_SEED,
        "debugging_problem_solving": AI_DEBUG_SEED,
    }
    core_overrides = {
        "project_overview": AI_PROJECT_OVERVIEW_CORE,
        "apis_backend": (
            "Once your model is trained and ready, how would you expose it through "
            "an API, including request, response, and error handling?"
        ),
        "deployment": (
            "How would you deploy a small AI model and monitor latency, errors, "
            "and model performance after release?"
        ),
        "debugging_problem_solving": (
            "Suppose your AI pipeline starts giving poor results. How would you "
            "debug whether the issue is in the data, preprocessing, model, or evaluation?"
        ),
    }
    packs = _pack_fields(
        JUNIOR_AI_BLUEPRINT,
        seed_overrides=seed_overrides,
        core_overrides=core_overrides,
    )
    return RoleConfig(
        key="junior_ai_engineer",
        display_title="Junior AI Engineer",
        blueprint=JUNIOR_AI_BLUEPRINT,
        default_profile=dict(DEFAULT_CANDIDATE_PROFILE),
        max_turns_per_domain=MAX_TURNS_PER_DOMAIN,
        max_probes_per_domain=MAX_PROBES_PER_DOMAIN,
        max_total_interview_turns=MAX_TOTAL_INTERVIEW_TURNS,
        max_context_followups_total=MAX_CONTEXT_FOLLOWUPS_TOTAL,
        max_skips_per_interview=MAX_SKIPS_PER_INTERVIEW,
        **packs,
    )


def build_junior_frontend_developer() -> RoleConfig:
    packs = _pack_fields(JUNIOR_FRONTEND_BLUEPRINT)
    return RoleConfig(
        key="junior_frontend_developer",
        display_title="Junior Frontend Developer",
        blueprint=JUNIOR_FRONTEND_BLUEPRINT,
        default_profile=dict(FRONTEND_DEFAULT_PROFILE),
        **packs,
    )


def build_junior_backend_developer() -> RoleConfig:
    packs = _pack_fields(JUNIOR_BACKEND_BLUEPRINT)
    return RoleConfig(
        key="junior_backend_developer",
        display_title="Junior Backend Developer",
        blueprint=JUNIOR_BACKEND_BLUEPRINT,
        default_profile=dict(BACKEND_DEFAULT_PROFILE),
        **packs,
    )
