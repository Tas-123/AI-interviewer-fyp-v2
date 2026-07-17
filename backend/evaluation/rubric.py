"""
Central evaluation rubric — single source of truth for scoring weights and hire thresholds.

Phase 4: used by evaluator, analytics, recruiter reports, and human-study export.
"""

from __future__ import annotations

from typing import Any

# Version tag included in reports for thesis reproducibility
RUBRIC_VERSION = "1.0"
EVALUATION_METHOD_NAME = "llm_rubric_ensemble_lite_v1"

# Dimension weights (must sum to 1.0)
DIMENSION_WEIGHTS: dict[str, float] = {
    "structure": 0.25,
    "result_orientation": 0.20,
    "ownership": 0.20,
    "leadership": 0.15,
    "clarity": 0.10,
    "confidence": 0.10,
}

SCORE_DIMENSIONS: tuple[str, ...] = (
    "clarity",
    "structure",
    "confidence",
    "ownership",
    "leadership",
    "result_orientation",
)

# Phase 6C — separated score profiles for reporting (not separate eval engines).
COMMUNICATION_DIMENSIONS: tuple[str, ...] = ("clarity", "structure", "confidence")
TECHNICAL_DIMENSIONS: tuple[str, ...] = ("ownership", "leadership", "result_orientation")

# Reduced communication weight when STT noise is high (Phase 6B fairness).
# Slightly favor technical dims so stuttery transcripts are less punished.
NOISY_TRANSCRIPT_WEIGHTS: dict[str, float] = {
    "structure": 0.10,
    "result_orientation": 0.28,
    "ownership": 0.28,
    "leadership": 0.18,
    "clarity": 0.04,
    "confidence": 0.12,
}

NOISY_TRANSCRIPT_THRESHOLD = 0.42


def should_apply_transcript_quality_adjustment(
    transcript_quality: dict[str, Any] | None,
) -> bool:
    """True when STT artifacts likely distorted communication scoring."""
    if not transcript_quality:
        return False
    if transcript_quality.get("is_noisy"):
        return True
    flags = set(transcript_quality.get("flags") or [])
    if flags & {"stutter_prefix", "likely_tail_fragment", "high_cleanup_reduction"}:
        return True
    if float(transcript_quality.get("reduction_ratio") or 0) >= 0.20:
        return True
    if float(transcript_quality.get("repeated_token_ratio") or 0) >= 0.22:
        return True
    if bool(transcript_quality.get("stutter_prefix")):
        return True
    if bool(transcript_quality.get("is_likely_tail_fragment")):
        return True
    return False


# Per-answer hire signal thresholds (weighted score)
HIRE_SIGNAL_THRESHOLDS: dict[str, float] = {
    "strong_hire": 4.2,
    "hire": 3.4,
    "borderline": 2.5,
}

# Recruiter aggregate recommendation tiers
RECRUITER_HIRE_THRESHOLDS: dict[str, float] = {
    "strong_hire": 4.0,
    "hire": 3.0,
    "lean_hire": 2.0,
}

# Rethink ensemble triggers (SWE-Judge lite — second pass on uncertain scores)
RETHINK_WEIGHTED_MIN = 2.2
RETHINK_WEIGHTED_MAX = 3.5

# High variance between dimensions also triggers rethink
RETHINK_DIMENSION_SPREAD_MIN = 1.5


def compute_weighted_score(scores: dict[str, Any]) -> float:
    """Compute weighted overall score from dimension scores."""
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        total += float(scores.get(dim, 0) or 0) * weight
    return round(total, 2)


def compute_weighted_score_with_weights(
    scores: dict[str, Any], weights: dict[str, float]
) -> float:
    """Compute weighted score with an alternate weight map."""
    total = 0.0
    for dim, weight in weights.items():
        total += float(scores.get(dim, 0) or 0) * weight
    return round(total, 2)


def compute_profile_scores(scores: dict[str, Any]) -> dict[str, Any]:
    """Aggregate communication vs technical composites for reporting."""
    comm_vals = [float(scores.get(d, 0) or 0) for d in COMMUNICATION_DIMENSIONS]
    tech_vals = [float(scores.get(d, 0) or 0) for d in TECHNICAL_DIMENSIONS]
    comm_avg = round(sum(comm_vals) / len(comm_vals), 2) if comm_vals else 0.0
    tech_avg = round(sum(tech_vals) / len(tech_vals), 2) if tech_vals else 0.0
    return {
        "communication": {
            "clarity": float(scores.get("clarity", 0) or 0),
            "structure": float(scores.get("structure", 0) or 0),
            "confidence": float(scores.get("confidence", 0) or 0),
            "composite": comm_avg,
        },
        "technical": {
            "ownership": float(scores.get("ownership", 0) or 0),
            "leadership": float(scores.get("leadership", 0) or 0),
            "result_orientation": float(scores.get("result_orientation", 0) or 0),
            "composite": tech_avg,
        },
    }


def apply_transcript_quality_adjustment(
    evaluation: dict[str, Any], transcript_quality: dict[str, Any] | None
) -> dict[str, Any]:
    """
    Re-weight scores when STT noise likely inflated communication penalties.

    Does not change the evaluation engine contract — adjusts post-primary scoring.
    """
    if not evaluation or not transcript_quality:
        return evaluation

    if not should_apply_transcript_quality_adjustment(transcript_quality):
        return evaluation

    adjusted = dict(evaluation)
    adjusted["weighted_overall_score"] = compute_weighted_score_with_weights(
        adjusted, NOISY_TRANSCRIPT_WEIGHTS
    )
    adjusted["hire_signal"] = derive_hire_signal(adjusted["weighted_overall_score"])
    adjusted["transcript_quality_adjusted"] = True
    adjusted["transcript_quality"] = transcript_quality
    adjusted["score_profiles"] = compute_profile_scores(adjusted)
    return adjusted


def aggregate_profile_scores(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """Average communication vs technical profiles across scored turns."""
    if not evaluations:
        return {
            "communication": {"composite": 0.0},
            "technical": {"composite": 0.0},
            "turns_included": 0,
        }

    comm_composites: list[float] = []
    tech_composites: list[float] = []
    comm_dims = {d: [] for d in COMMUNICATION_DIMENSIONS}
    tech_dims = {d: [] for d in TECHNICAL_DIMENSIONS}

    for ev in evaluations:
        if float(ev.get("overall_score", 0) or 0) <= 0:
            continue
        profiles = ev.get("score_profiles") or compute_profile_scores(ev)
        comm_composites.append(float(profiles["communication"]["composite"]))
        tech_composites.append(float(profiles["technical"]["composite"]))
        for d in COMMUNICATION_DIMENSIONS:
            comm_dims[d].append(float(ev.get(d, 0) or 0))
        for d in TECHNICAL_DIMENSIONS:
            tech_dims[d].append(float(ev.get(d, 0) or 0))

    def _avg(vals: list[float]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "communication": {
            **{d: _avg(comm_dims[d]) for d in COMMUNICATION_DIMENSIONS},
            "composite": _avg(comm_composites),
        },
        "technical": {
            **{d: _avg(tech_dims[d]) for d in TECHNICAL_DIMENSIONS},
            "composite": _avg(tech_composites),
        },
        "turns_included": len(comm_composites),
    }


def derive_hire_signal(weighted_score: float) -> str:
    """Map weighted score to per-answer hire signal."""
    if weighted_score >= HIRE_SIGNAL_THRESHOLDS["strong_hire"]:
        return "Strong Hire"
    if weighted_score >= HIRE_SIGNAL_THRESHOLDS["hire"]:
        return "Hire"
    if weighted_score >= HIRE_SIGNAL_THRESHOLDS["borderline"]:
        return "Borderline"
    return "No Hire"


def should_trigger_rethink(evaluation: dict[str, Any]) -> bool:
    """
    Return True when a second scoring pass may stabilize an uncertain evaluation.

    Triggers:
    - Weighted score in borderline band
    - Large spread between best and worst dimension
    """
    weighted = float(
        evaluation.get("weighted_overall_score", evaluation.get("overall_score", 0)) or 0
    )
    if RETHINK_WEIGHTED_MIN <= weighted <= RETHINK_WEIGHTED_MAX:
        return True

    dim_scores = [float(evaluation.get(dim, 0) or 0) for dim in SCORE_DIMENSIONS]
    valid = [s for s in dim_scores if s > 0]
    if len(valid) >= 2 and (max(valid) - min(valid)) >= RETHINK_DIMENSION_SPREAD_MIN:
        return True

    return False


def merge_evaluations(primary: dict, rethink: dict) -> dict:
    """
    Merge primary and rethink evaluations (conservative average per dimension).

    Recomputes overall, weighted score, weakest dimension, and hire signal.
    """
    merged = dict(primary)
    for dim in SCORE_DIMENSIONS:
        p = float(primary.get(dim, 0) or 0)
        r = float(rethink.get(dim, 0) or 0)
        merged[dim] = round((p + r) / 2, 2)

    scores = [merged[d] for d in SCORE_DIMENSIONS]
    merged["overall_score"] = round(sum(scores) / len(scores), 2)
    merged["weighted_overall_score"] = compute_weighted_score(merged)

    min_score = min(scores)
    merged["weakest_dimension"] = SCORE_DIMENSIONS[scores.index(min_score)]
    merged["hire_signal"] = derive_hire_signal(merged["weighted_overall_score"])

    # Merge strengths/weaknesses uniquely
    merged["strengths"] = list(dict.fromkeys(
        (primary.get("strengths") or []) + (rethink.get("strengths") or [])
    ))[:5]
    merged["weaknesses"] = list(dict.fromkeys(
        (primary.get("weaknesses") or []) + (rethink.get("weaknesses") or [])
    ))[:5]

    star = primary.get("star_breakdown") or {}
    rethink_star = rethink.get("star_breakdown") or {}
    merged["star_breakdown"] = {
        k: bool(star.get(k, False) or rethink_star.get(k, False))
        for k in ("situation_present", "task_present", "action_present", "result_present")
    }
    merged["ensemble_merged"] = True
    return merged


def get_evaluation_methodology() -> dict[str, Any]:
    """Metadata block for reports and thesis documentation."""
    return {
        "method": EVALUATION_METHOD_NAME,
        "rubric_version": RUBRIC_VERSION,
        "dimensions": list(SCORE_DIMENSIONS),
        "dimension_weights": dict(DIMENSION_WEIGHTS),
        "hire_signal_thresholds": dict(HIRE_SIGNAL_THRESHOLDS),
        "ensemble": {
            "strategy": "primary_llm_score + optional_rethink_pass",
            "rethink_trigger": {
                "weighted_score_range": [RETHINK_WEIGHTED_MIN, RETHINK_WEIGHTED_MAX],
                "dimension_spread_min": RETHINK_DIMENSION_SPREAD_MIN,
            },
            "merge_strategy": "dimension_average",
        },
        "note": (
            "Lite ensemble inspired by SWE-Judge rethink — a second LLM pass runs only "
            "when the primary score is borderline or dimension spread is high."
        ),
        "score_profiles": {
            "communication_dimensions": list(COMMUNICATION_DIMENSIONS),
            "technical_dimensions": list(TECHNICAL_DIMENSIONS),
            "noisy_transcript_reweight": "communication dimensions down-weighted when STT noise is high",
        },
    }
