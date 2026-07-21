"""
Question deduplication — prevent repeating the same interview question.

Phase 6A: detects canonical domain questions and near-duplicate wording.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Signature phrases that identify a domain's primary question (any match = already asked).
DOMAIN_PRIMARY_SIGNATURES: dict[str, tuple[str, ...]] = {
    "project_overview": (
        "ai or machine learning project",
        "project you worked on",
        "briefly explain one",
    ),
    "python": (
        "organize the code",
        "python project structure",
        "clean, reusable, and easy to debug",
    ),
    "machine_learning": (
        "detect overfitting",
        "training score is high but validation",
    ),
    "data_preprocessing": (
        "missing values, categorical",
        "handle missing values",
    ),
    "model_evaluation": (
        "accuracy, precision, recall",
        "choose between accuracy",
    ),
    "nlp_speech_ai": ("speech or nlp", "preprocessing would you apply"),
    "apis_backend": ("expose it through an api", "expose a trained ai model"),
    "deployment": ("deploy a small ai model", "monitor its latency"),
    "debugging_problem_solving": ("debug whether the issue", "poor results"),
    "behavioral_ownership": ("took ownership", "technical problem"),
    # Frontend
    "html_css": (
        "responsive page layout",
        "html and css",
        "desktop and mobile",
    ),
    "javascript": (
        "asynchronous work",
        "fetching data from an api",
        "async/await",
    ),
    "react_frontend": (
        "structure components and state",
        "lift state up",
        "in react",
    ),
    "frontend_apis": (
        "call a backend api from the browser",
        "loading or empty states",
        "handle errors",
    ),
    # Backend
    "backend_language": (
        "organize a small service",
        "handlers, business logic",
        "data access stay separate",
    ),
    "databases": (
        "relational schema",
        "fetch related records",
        "join or equivalent",
    ),
    "auth_security": (
        "add authentication to an api",
        "protect a private endpoint",
        "unauthorized access",
    ),
}

# Legacy single-needle map (kept for backward compatibility).
DOMAIN_CANONICAL_QUESTIONS: dict[str, str] = {
    k: v[0] for k, v in DOMAIN_PRIMARY_SIGNATURES.items()
}


def normalize_question(text: str) -> str:
    """Lowercase, strip labels, collapse whitespace for comparison."""
    if not text:
        return ""
    cleaned = text.lower()
    for label in ("[follow-up]", "[follow up]", "follow-up:", "follow up:"):
        cleaned = cleaned.replace(label, "")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def similarity(a: str, b: str) -> float:
    """Return 0–1 similarity between two normalized question strings."""
    na, nb = normalize_question(a), normalize_question(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def is_semantic_duplicate(candidate: str, history: list[str], threshold: float = 0.80) -> bool:
    """True if candidate closely matches any prior question."""
    for prior in history or []:
        if similarity(candidate, prior) >= threshold:
            return True
    return False


def domain_primary_already_asked(domain: str, history: list[str]) -> bool:
    """True if this domain's canonical primary question already appears in history."""
    signatures = DOMAIN_PRIMARY_SIGNATURES.get((domain or "").lower(), ())
    if not signatures:
        return False
    for q in history or []:
        nq = normalize_question(q)
        for sig in signatures:
            norm_sig = normalize_question(sig)
            if norm_sig in nq or similarity(nq, norm_sig) >= 0.72:
                return True
    return False
