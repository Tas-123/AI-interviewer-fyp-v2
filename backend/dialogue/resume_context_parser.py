"""
Resume Context Parser — Extracts structured candidate data from resume text.

Provides deterministic keyword/pattern extraction without LLM dependency.
Used by the question selector and bounded domain question generation.
"""

from __future__ import annotations

import re


# ── Known technology/tool keywords ──────────────────────────────
KNOWN_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "c#", "go",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r",
    "react", "angular", "vue", "next.js", "node.js", "express",
    "django", "flask", "fastapi", "spring", "rails",
    "sql", "postgresql", "postgres", "mysql", "mongodb", "redis",
    "elasticsearch", "dynamodb", "sqlite",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "ci/cd", "jenkins", "github actions", "gitlab",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "rest api", "graphql", "grpc", "microservices",
    "git", "linux", "agile", "scrum", "jira",
    "html", "css", "tailwind", "bootstrap",
    "qdrant", "embeddings", "speaker recognition", "speech recognition",
    "whisper", "transformers", "huggingface", "langchain",
]

KNOWN_ROLES = [
    "software engineer", "backend engineer", "frontend engineer",
    "full stack developer", "full-stack developer",
    "data scientist", "data engineer", "ml engineer",
    "devops engineer", "site reliability engineer", "sre",
    "product manager", "project manager", "tech lead",
    "engineering manager", "architect", "qa engineer",
    "mobile developer", "ios developer", "android developer",
    "junior ai engineer", "ai engineer",
]

# Experience pattern: "X years" or "X+ years"
EXPERIENCE_PATTERN = re.compile(
    r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience)?",
    re.IGNORECASE,
)

# Map resume keywords → blueprint domains for personalization.
DOMAIN_KEYWORD_MAP: dict[str, tuple[str, ...]] = {
    "project_overview": (
        "project", "built", "developed", "speaker recognition", "chatbot",
        "pipeline", "application",
    ),
    "python": (
        "python", "django", "flask", "fastapi", "pandas", "numpy",
        "scikit-learn", "pytest",
    ),
    "machine_learning": (
        "machine learning", "deep learning", "tensorflow", "pytorch",
        "xgboost", "random forest", "cnn", "lstm", "transformer",
        "overfitting", "training",
    ),
    "data_preprocessing": (
        "preprocessing", "feature", "missing values", "encoding",
        "scaling", "pandas", "etl",
    ),
    "model_evaluation": (
        "accuracy", "precision", "recall", "f1", "confusion matrix",
        "evaluation", "validation", "metrics",
    ),
    "nlp_speech_ai": (
        "nlp", "speech", "speaker recognition", "whisper", "embeddings",
        "qdrant", "tokenization", "huggingface", "transformers",
        "text", "audio", "asr", "tts",
    ),
    "apis_backend": (
        "fastapi", "flask", "django", "api", "rest", "endpoint",
        "backend", "graphql",
    ),
    "deployment": (
        "docker", "kubernetes", "aws", "azure", "gcp", "deploy",
        "ci/cd", "monitoring", "latency",
    ),
    "debugging_problem_solving": (
        "debug", "logging", "troubleshoot", "bug", "issue",
    ),
    "behavioral_ownership": (
        "led", "ownership", "team", "collaboration", " mentored",
    ),
}


def parse_resume(resume_text: str) -> dict:
    """
    Extract structured candidate data from resume text.

    Returns:
        {
            "candidate_skills": [...],
            "candidate_tools": [...],
            "candidate_experience": "X years" or "not specified",
            "candidate_role": "detected role" or "not specified",
            "candidate_projects": [...],
        }
    """
    if not resume_text or not isinstance(resume_text, str):
        return {
            "candidate_skills": [],
            "candidate_tools": [],
            "candidate_experience": "not specified",
            "candidate_role": "not specified",
            "candidate_projects": [],
        }

    text_lower = resume_text.lower()

    found_skills = []
    found_tools = []
    for skill in KNOWN_SKILLS:
        if len(skill) <= 3:
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, text_lower):
                if skill in {"git", "sql", "aws", "gcp", "css", "r"}:
                    found_tools.append(skill)
                else:
                    found_skills.append(skill)
        else:
            if skill in text_lower:
                tools_keywords = {
                    "docker", "kubernetes", "terraform", "jenkins",
                    "github actions", "gitlab", "jira", "redis",
                    "elasticsearch", "dynamodb", "sqlite",
                    "tailwind", "bootstrap", "qdrant",
                }
                if skill in tools_keywords:
                    found_tools.append(skill)
                else:
                    found_skills.append(skill)

    exp_match = EXPERIENCE_PATTERN.search(resume_text)
    experience = f"{exp_match.group(1)} years" if exp_match else "not specified"

    detected_role = "not specified"
    for role in KNOWN_ROLES:
        if role in text_lower:
            detected_role = role.title()
            break

    projects = extract_projects(resume_text)

    return {
        "candidate_skills": list(set(found_skills)),
        "candidate_tools": list(set(found_tools)),
        "candidate_experience": experience,
        "candidate_role": detected_role,
        "candidate_projects": projects,
    }


def extract_projects(resume_text: str) -> list[str]:
    """Pull simple project phrases from free-text resume summaries."""
    if not resume_text or not isinstance(resume_text, str):
        return []

    projects: list[str] = []
    seen: set[str] = set()

    # Bullet / line oriented snippets.
    for raw_line in resume_text.splitlines():
        line = raw_line.strip(" -•*\t")
        if len(line) < 8 or len(line) > 160:
            continue
        lower = line.lower()
        if any(
            m in lower
            for m in (
                "project",
                "built",
                "developed",
                "implemented",
                "worked on",
                "created",
            )
        ):
            key = lower[:80]
            if key not in seen:
                seen.add(key)
                projects.append(line)

    # Sentence patterns when there are no newlines (textarea summary).
    if not projects:
        sentences = re.split(r"(?<=[.!?])\s+", resume_text.strip())
        for sent in sentences:
            s = sent.strip()
            lower = s.lower()
            if len(s) < 12 or len(s) > 180:
                continue
            if any(
                m in lower
                for m in (
                    "project",
                    "built",
                    "developed",
                    "speaker recognition",
                    "chatbot",
                    "worked on",
                )
            ):
                key = lower[:80]
                if key not in seen:
                    seen.add(key)
                    projects.append(s)

    return projects[:5]


def map_resume_to_domains(
    *,
    skills: list[str] | None = None,
    tools: list[str] | None = None,
    projects: list[str] | None = None,
    resume_text: str = "",
) -> dict[str, list[str]]:
    """
    Map resume evidence to blueprint domains.

    Returns {domain_id: [evidence snippets...]}.
    """
    blob_parts = [
        " ".join(skills or []),
        " ".join(tools or []),
        " ".join(projects or []),
        resume_text or "",
    ]
    blob = " ".join(blob_parts).lower()
    result: dict[str, list[str]] = {}

    for domain, keywords in DOMAIN_KEYWORD_MAP.items():
        hits: list[str] = []
        for kw in keywords:
            if kw in blob:
                hits.append(kw)
        # Attach concrete project lines that mention domain keywords.
        for project in projects or []:
            pl = project.lower()
            if any(kw in pl for kw in keywords):
                if project not in hits:
                    hits.append(project)
        if hits:
            # Prefer project lines first, then keywords.
            ordered = [h for h in hits if len(h) > 20] + [
                h for h in hits if len(h) <= 20
            ]
            # Dedupe preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for item in ordered:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
            result[domain] = unique[:4]

    return result


def generate_resume_questions(parsed_resume: dict) -> list:
    """
    Generate personalized interview questions from parsed resume data.

    Returns list of {"domain": str, "question": str} for domain-aware selection.
    """
    questions: list[dict] = []
    skills = parsed_resume.get("candidate_skills", [])
    tools = parsed_resume.get("candidate_tools", [])
    projects = parsed_resume.get("candidate_projects", [])
    role = parsed_resume.get("candidate_role", "not specified")
    experience = parsed_resume.get("candidate_experience", "not specified")

    for project in projects[:3]:
        questions.append(
            {
                "domain": "project_overview",
                "question": (
                    f"You mentioned: {project}. "
                    "What problem did it solve, what did you build, and what was the result?"
                ),
            }
        )

    skill_domain = {
        "python": "python",
        "fastapi": "apis_backend",
        "flask": "apis_backend",
        "django": "apis_backend",
        "docker": "deployment",
        "kubernetes": "deployment",
        "aws": "deployment",
        "nlp": "nlp_speech_ai",
        "speech recognition": "nlp_speech_ai",
        "speaker recognition": "nlp_speech_ai",
        "tensorflow": "machine_learning",
        "pytorch": "machine_learning",
        "machine learning": "machine_learning",
        "scikit-learn": "machine_learning",
        "pandas": "data_preprocessing",
    }

    for skill in skills[:5]:
        domain = skill_domain.get(skill.lower(), "project_overview")
        questions.append(
            {
                "domain": domain,
                "question": (
                    f"You mentioned {skill.title()} in your background. "
                    f"Can you describe how you used {skill.title()} "
                    f"in a real project?"
                ),
            }
        )

    for tool in tools[:3]:
        domain = skill_domain.get(tool.lower(), "deployment")
        questions.append(
            {
                "domain": domain,
                "question": (
                    f"Tell me about your experience with {tool.title()}. "
                    f"How have you used it in a project or production setting?"
                ),
            }
        )

    if role != "not specified":
        questions.append(
            {
                "domain": "behavioral_ownership",
                "question": (
                    f"As a {role}, what do you consider the most critical "
                    f"skill for success in this kind of role?"
                ),
            }
        )

    if experience != "not specified":
        questions.append(
            {
                "domain": "behavioral_ownership",
                "question": (
                    f"With {experience} of experience, what is the most "
                    f"important lesson you have learned while building AI systems?"
                ),
            }
        )

    return questions
