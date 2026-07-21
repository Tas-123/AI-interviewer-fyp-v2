"""
Shared domain vocabulary for multi-role interview blueprints.

Domain ids are the allowlist used by curated templates and the InterviewSpec
compiler. CoverageEngine treats them as opaque strings; packs supply seeds,
labels, hints, and resume keyword maps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DomainDef:
    """One interview domain in the shared allowlist."""

    id: str
    label: str
    seed: str
    hint: str
    keywords: tuple[str, ...] = ()
    skill_aliases: tuple[str, ...] = ()
    is_technical: bool = True
    is_high_value: bool = False
    # Optional spoken core used by naturalizer (defaults to seed).
    spoken_core: str = ""


def _d(
    id: str,
    label: str,
    seed: str,
    hint: str,
    *,
    keywords: tuple[str, ...] = (),
    skill_aliases: tuple[str, ...] = (),
    is_technical: bool = True,
    is_high_value: bool = False,
    spoken_core: str = "",
) -> DomainDef:
    return DomainDef(
        id=id,
        label=label,
        seed=seed,
        hint=hint,
        keywords=keywords,
        skill_aliases=skill_aliases,
        is_technical=is_technical,
        is_high_value=is_high_value,
        spoken_core=spoken_core or seed,
    )


# ── Shared / cross-role domains ─────────────────────────────────

DOMAIN_DEFS: dict[str, DomainDef] = {
    "project_overview": _d(
        "project_overview",
        "Project Overview",
        "Briefly explain one technical project you worked on. "
        "What problem did it solve, what did you build, and what was the result?",
        "Think of one project — even a small one. What problem did it solve and what did you build?",
        keywords=(
            "project", "built", "developed", "application", "pipeline", "portfolio",
        ),
        is_technical=False,
        is_high_value=True,
        spoken_core=(
            "Briefly explain one technical project you worked on. "
            "What problem did it solve, what did you build, and what was the result?"
        ),
    ),
    "debugging_problem_solving": _d(
        "debugging_problem_solving",
        "Debugging & Problem Solving",
        "When a feature or pipeline starts failing, how do you debug whether the "
        "issue is in the data, code, integration, or environment?",
        "Check inputs first, then logs, then the failing step end to end.",
        keywords=("debug", "logging", "troubleshoot", "bug", "issue"),
        skill_aliases=("debugging", "troubleshooting"),
        is_high_value=False,
    ),
    "behavioral_ownership": _d(
        "behavioral_ownership",
        "Behavioral / Ownership",
        "Tell me about a time you took ownership of a technical problem. "
        "What did you do, and what was the outcome?",
        "Pick a small problem you personally fixed — what you did and what changed.",
        keywords=("led", "ownership", "team", "collaboration", "mentored"),
        is_technical=False,
        is_high_value=False,
    ),
    "apis_backend": _d(
        "apis_backend",
        "APIs / Backend",
        "How would you design a REST API endpoint, including request, response, "
        "and basic error handling?",
        "A REST endpoint, request/response JSON schema, and basic error handling.",
        keywords=(
            "fastapi", "flask", "django", "api", "rest", "endpoint",
            "backend", "graphql", "express", "node.js",
        ),
        skill_aliases=(
            "fastapi", "flask", "django", "rest api", "graphql",
            "express", "node.js", "nodejs",
        ),
        is_high_value=True,
        spoken_core=(
            "Once a service is ready, how would you expose it through an API, "
            "including request, response, and error handling?"
        ),
    ),
    "deployment": _d(
        "deployment",
        "Deployment",
        "What steps would you take to deploy a small web service and monitor "
        "latency, errors, and uptime after release?",
        "Containerize the app, expose an endpoint, and watch logs plus latency.",
        keywords=(
            "docker", "kubernetes", "aws", "azure", "gcp", "deploy",
            "ci/cd", "monitoring", "latency",
        ),
        skill_aliases=(
            "docker", "kubernetes", "aws", "azure", "gcp", "ci/cd",
            "jenkins", "github actions",
        ),
        is_high_value=True,
    ),
    # ── Junior AI Engineer domains ──────────────────────────────
    "python": _d(
        "python",
        "Python",
        "In Python, how would you structure a small machine learning project so the "
        "code stays clean, reusable, and easy to debug?",
        "Consider folders like src/, a config file, and main.py — how would you lay those out?",
        keywords=(
            "python", "django", "flask", "fastapi", "pandas", "numpy",
            "scikit-learn", "pytest",
        ),
        skill_aliases=("python",),
        is_high_value=True,
        spoken_core=(
            "In a small ML project, how would you organize the code so it stays "
            "clean, reusable, and easy to debug?"
        ),
    ),
    "machine_learning": _d(
        "machine_learning",
        "Machine Learning",
        "How would you detect overfitting in a machine learning model, and what "
        "steps would you take to reduce it?",
        "Compare training accuracy to validation accuracy, and mention regularization or more data.",
        keywords=(
            "machine learning", "deep learning", "tensorflow", "pytorch",
            "xgboost", "random forest", "cnn", "lstm", "transformer",
            "overfitting", "training",
        ),
        skill_aliases=(
            "machine learning", "deep learning", "tensorflow", "pytorch",
            "scikit-learn",
        ),
        is_high_value=True,
        spoken_core=(
            "Suppose your training score is high but validation performance drops. "
            "How would you detect overfitting, and what would you do to reduce it?"
        ),
    ),
    "data_preprocessing": _d(
        "data_preprocessing",
        "Data Preprocessing",
        "How would you handle missing values, categorical features, and scaling "
        "before training a machine learning model?",
        "Missing values can use mean/median imputation; categoricals can use encoding; numerics can be scaled.",
        keywords=(
            "preprocessing", "feature", "missing values", "encoding",
            "scaling", "pandas", "etl",
        ),
        skill_aliases=("pandas", "numpy", "data preprocessing"),
        spoken_core=(
            "Before training a model, how would you handle missing values, "
            "categorical features, and scaling?"
        ),
    ),
    "model_evaluation": _d(
        "model_evaluation",
        "Model Evaluation",
        "For a classification model, how would you choose evaluation metrics such as "
        "accuracy, precision, recall, F1-score, and confusion matrix?",
        "Accuracy for balance; precision/recall when false positives or false negatives matter; F1 combines both.",
        keywords=(
            "accuracy", "precision", "recall", "f1", "confusion matrix",
            "evaluation", "validation", "metrics",
        ),
        skill_aliases=("model evaluation",),
        spoken_core=(
            "For a classification model, how would you choose between accuracy, "
            "precision, recall, F1-score, and the confusion matrix?"
        ),
    ),
    "nlp_speech_ai": _d(
        "nlp_speech_ai",
        "NLP / Speech AI",
        "If you are building a speech or NLP-based AI system, what preprocessing "
        "steps would you apply before sending text to the model?",
        "Think tokenization, normalization, and handling audio or text noise before the model.",
        keywords=(
            "nlp", "speech", "speaker recognition", "whisper", "embeddings",
            "qdrant", "tokenization", "huggingface", "transformers",
            "text", "audio", "asr", "tts", "computer vision",
        ),
        skill_aliases=(
            "nlp", "speech recognition", "speaker recognition", "computer vision",
            "whisper", "transformers",
        ),
        spoken_core=(
            "Suppose you're building a speech or NLP-based AI system. "
            "What preprocessing would you apply before sending the text to the model?"
        ),
    ),
    # ── Frontend domains ────────────────────────────────────────
    "html_css": _d(
        "html_css",
        "HTML / CSS",
        "How would you structure a responsive page layout with HTML and CSS so it "
        "works well on both desktop and mobile?",
        "Think semantic HTML, a simple layout, and media queries for smaller screens.",
        keywords=("html", "css", "responsive", "flexbox", "grid", "tailwind", "bootstrap"),
        skill_aliases=("html", "css", "tailwind", "bootstrap"),
        is_high_value=True,
    ),
    "javascript": _d(
        "javascript",
        "JavaScript",
        "In JavaScript, how would you handle asynchronous work such as fetching "
        "data from an API and updating the UI safely?",
        "Mention fetch or async/await, and how you handle loading and errors.",
        keywords=("javascript", "typescript", "async", "promise", "dom"),
        skill_aliases=("javascript", "typescript", "js"),
        is_high_value=True,
    ),
    "react_frontend": _d(
        "react_frontend",
        "React / Frontend Framework",
        "In React, how would you structure components and state for a small "
        "interactive feature, and when would you lift state up?",
        "Think of parent/child components and where shared state should live.",
        keywords=("react", "vue", "angular", "next.js", "component", "hooks"),
        skill_aliases=("react", "vue", "angular", "next.js"),
        is_high_value=True,
    ),
    "frontend_apis": _d(
        "frontend_apis",
        "Frontend API Integration",
        "How would you call a backend API from the browser, handle errors, and "
        "show loading or empty states to the user?",
        "Describe fetch/axios, status codes, and what the user sees while waiting.",
        keywords=("fetch", "axios", "api", "cors", "json"),
        skill_aliases=("axios", "rest api"),
        is_high_value=True,
    ),
    # ── Backend domains ─────────────────────────────────────────
    "backend_language": _d(
        "backend_language",
        "Backend Language",
        "In your main backend language, how would you organize a small service "
        "so handlers, business logic, and data access stay separate?",
        "Think routes/controllers, services, and a data layer.",
        keywords=("python", "node.js", "java", "go", "backend"),
        skill_aliases=("python", "node.js", "nodejs", "java", "go"),
        is_high_value=True,
    ),
    "databases": _d(
        "databases",
        "Databases",
        "How would you design a simple relational schema and write a query to "
        "fetch related records efficiently?",
        "Mention tables, keys, and a JOIN or equivalent lookup.",
        keywords=(
            "sql", "postgresql", "postgres", "mysql", "mongodb", "redis",
            "database", "schema",
        ),
        skill_aliases=(
            "sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "sqlite",
        ),
        is_high_value=True,
    ),
    "auth_security": _d(
        "auth_security",
        "Auth & Security",
        "How would you add authentication to an API and protect a private endpoint "
        "from unauthorized access?",
        "Think tokens or sessions, password hashing, and checking auth on the route.",
        keywords=("auth", "jwt", "oauth", "security", "password", "session"),
        skill_aliases=("jwt", "oauth", "authentication"),
        is_high_value=True,
    ),
}


# AI-specific project overview seed (used by junior_ai_engineer template).
AI_PROJECT_OVERVIEW_SEED = (
    "Briefly explain one AI or machine learning project you worked on. "
    "What problem did it solve, what did you build, and what was the result?"
)
AI_PROJECT_OVERVIEW_CORE = AI_PROJECT_OVERVIEW_SEED
AI_DEBUG_SEED = (
    "If your AI pipeline gives poor results, how would you debug whether the "
    "issue is in the data, preprocessing, model, or evaluation?"
)
AI_API_SEED = (
    "How would you expose a trained AI model through an API, and what request, "
    "response, and error-handling details would you include?"
)
AI_DEPLOY_SEED = (
    "What steps would you take to deploy a small AI model and monitor its "
    "latency, errors, and performance after deployment?"
)


def get_domain(domain_id: str) -> DomainDef | None:
    return DOMAIN_DEFS.get((domain_id or "").strip().lower())


def seeds_for(blueprint: Iterable[str], *, overrides: dict[str, str] | None = None) -> dict[str, str]:
    overrides = overrides or {}
    out: dict[str, str] = {}
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        if key in overrides:
            out[key] = overrides[key]
            continue
        d = DOMAIN_DEFS.get(key)
        if d:
            out[key] = d.seed
    return out


def labels_for(blueprint: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        d = DOMAIN_DEFS.get(key)
        out[key] = d.label if d else key.replace("_", " ").title()
    return out


def hints_for(blueprint: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        d = DOMAIN_DEFS.get(key)
        if d:
            out[key] = d.hint
    return out


def spoken_cores_for(
    blueprint: Iterable[str], *, overrides: dict[str, str] | None = None
) -> dict[str, str]:
    overrides = overrides or {}
    out: dict[str, str] = {}
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        if key in overrides:
            out[key] = overrides[key]
            continue
        d = DOMAIN_DEFS.get(key)
        if d:
            out[key] = d.spoken_core
    return out


def technical_domains_for(blueprint: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        d = DOMAIN_DEFS.get(key)
        if d and d.is_technical:
            result.append(key)
    return tuple(result)


def high_value_domains_for(blueprint: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        d = DOMAIN_DEFS.get(key)
        if d and d.is_high_value:
            result.append(key)
    return tuple(result)


def keyword_map_for(blueprint: Iterable[str]) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        d = DOMAIN_DEFS.get(key)
        if d and d.keywords:
            out[key] = d.keywords
    return out


def skill_domain_map_for(blueprint: Iterable[str]) -> dict[str, str]:
    """Map skill/tool alias → domain id for resume question tagging."""
    allowed = {(d or "").strip().lower() for d in blueprint}
    out: dict[str, str] = {}
    for domain_id, d in DOMAIN_DEFS.items():
        if domain_id not in allowed:
            continue
        for alias in d.skill_aliases:
            out[alias.lower()] = domain_id
    return out


def all_domain_labels() -> dict[str, str]:
    return {k: v.label for k, v in DOMAIN_DEFS.items()}


def all_domain_hints() -> dict[str, str]:
    return {k: v.hint for k, v in DOMAIN_DEFS.items()}


def all_spoken_cores() -> dict[str, str]:
    return {k: v.spoken_core for k, v in DOMAIN_DEFS.items()}


def all_seeds() -> dict[str, str]:
    return {k: v.seed for k, v in DOMAIN_DEFS.items()}


def validate_blueprint(blueprint: Iterable[str]) -> list[str]:
    """Return unknown domain ids (empty if valid)."""
    unknown: list[str] = []
    for domain_id in blueprint:
        key = (domain_id or "").strip().lower()
        if key and key not in DOMAIN_DEFS:
            unknown.append(key)
    return unknown
