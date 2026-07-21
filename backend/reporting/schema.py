"""Report v2 schema constants and backward-compatibility keys."""

REPORT_VERSION = "2.0"

REPORT_TYPES = ("complete", "partial", "incomplete", "aborted")

TERMINATION_REASONS = (
    "natural_completion",
    "user_disconnect",
    "connection_lost",
    "error",
    "timeout",
)

# Legacy top-level keys mirrored for existing API/UI consumers.
LEGACY_TOP_LEVEL_KEYS = (
    "weighted_score_summary",
    "score_profile_summary",
    "technical_evidence_analysis",
    "performance_trend_analysis",
    "consistency_rating",
    "behavioral_profile",
    "recruiter_summary",
    "bias_awareness",
    "adaptive_questioning_trace",
    "skill_coverage_map",
    "domain_assessment_map",
    "interview_completion",
    "interview_metadata",
    "evaluation_methodology",
    "latency_metrics",
)

DOMAIN_LABELS = {}
try:
    from core.domain_packs import all_domain_labels

    DOMAIN_LABELS.update(all_domain_labels())
except Exception:
    DOMAIN_LABELS = {
        "project_overview": "Project Overview",
        "python": "Python",
        "machine_learning": "Machine Learning",
        "data_preprocessing": "Data Preprocessing",
        "model_evaluation": "Model Evaluation",
        "nlp_speech_ai": "NLP / Speech AI",
        "apis_backend": "APIs / Backend",
        "deployment": "Deployment",
        "debugging_problem_solving": "Debugging & Problem Solving",
        "behavioral_ownership": "Behavioral / Ownership",
    }


def domain_label(domain_id: str, role_labels: dict | None = None) -> str:
    """Resolve a human label for a domain id."""
    key = (domain_id or "").strip().lower()
    if isinstance(role_labels, dict) and key in role_labels:
        return role_labels[key]
    return DOMAIN_LABELS.get(key, key.replace("_", " ").title() if key else "Unknown")

PARTIAL_RECOMMENDATION_RATIONALE = (
    "Preliminary data only. Interview ended before sufficient assessment was "
    "completed to provide a defensible hiring signal."
)
