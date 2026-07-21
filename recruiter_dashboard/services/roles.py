"""
Static role list for the Recruiter dropdown and candidate lobby.

Kept local (not imported from backend) so the recruiter module stays
independent of the interview engine. Keep in sync with
backend/core/role_registry.py when new roles are added.
"""

from __future__ import annotations

DEFAULT_TARGET_ROLE = "junior_ai_engineer"

ROLE_OPTIONS: list[dict] = [
    {
        "key": "junior_ai_engineer",
        "display_title": "Junior AI Engineer",
        "description": (
            "A real-time voice interview for Junior AI Engineer candidates, "
            "with adaptive technical questions and an automated evaluation report."
        ),
        "suggested_skills": [
            "Python",
            "Machine Learning",
            "Deep Learning",
            "NLP",
            "Computer Vision",
            "FastAPI",
            "PyTorch",
            "TensorFlow",
            "Data Preprocessing",
            "Model Evaluation",
        ],
    },
    {
        "key": "junior_frontend_developer",
        "display_title": "Junior Frontend Developer",
        "description": (
            "A real-time voice interview for Junior Frontend Developer candidates, "
            "covering UI, JavaScript, frameworks, and API integration."
        ),
        "suggested_skills": [
            "HTML",
            "CSS",
            "JavaScript",
            "TypeScript",
            "React",
            "Next.js",
            "Vue",
            "Tailwind",
            "REST APIs",
            "Responsive Design",
        ],
    },
    {
        "key": "junior_backend_developer",
        "display_title": "Junior Backend Developer",
        "description": (
            "A real-time voice interview for Junior Backend Developer candidates, "
            "covering APIs, databases, auth, and deployment basics."
        ),
        "suggested_skills": [
            "Python",
            "Node.js",
            "FastAPI",
            "Express",
            "SQL",
            "PostgreSQL",
            "REST APIs",
            "Docker",
            "Authentication",
            "MongoDB",
        ],
    },
]


def list_roles() -> list[dict]:
    return [dict(r) for r in ROLE_OPTIONS]


def get_role_meta(target_role: str | None) -> dict:
    key = normalize_role(target_role)
    for r in ROLE_OPTIONS:
        if r["key"] == key:
            return dict(r)
    return dict(ROLE_OPTIONS[0])


def is_known_role(target_role: str) -> bool:
    key = (target_role or "").strip().lower()
    return any(r["key"] == key for r in ROLE_OPTIONS)


def normalize_role(target_role: str | None) -> str:
    key = (target_role or DEFAULT_TARGET_ROLE).strip().lower()
    if is_known_role(key):
        return key
    return DEFAULT_TARGET_ROLE
