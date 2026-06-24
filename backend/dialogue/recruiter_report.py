"""
Recruiter Report — HR-facing report generation and candidate ranking.

Transforms internal analytics data into structured recruiter-friendly outputs.
Does NOT modify the evaluation engine or analytics logic — reads only.
"""


def generate_hr_report(dm) -> dict:
    """
    Generate a structured recruiter-facing report from a DialogueManager.

    Args:
        dm: DialogueManager instance with completed (or in-progress) interview

    Returns:
        Dict with recruiter-friendly fields.
    """
    context = dm.context
    eval_summary = context.get_evaluation_summary()

    # Import analytics functions (read only)
    from dialogue.analytics import (
        detect_performance_trend,
        compute_consistency_rating,
        generate_behavioral_profile,
    )

    # ── Compute analytics ────────────────────────────────────────
    if context.weighted_score_history:
        trend = detect_performance_trend(context.weighted_score_history)
        consistency = compute_consistency_rating(context.weighted_score_history)
        trend_label = trend.get("performance_trend_label", "stable")
        consistency_rating = consistency.get("consistency_rating", "N/A")
    else:
        trend_label = "insufficient_data"
        consistency_rating = "N/A"

    # Filter valid scored evaluations
    scored = [e for e in context.evaluations
              if e.get("overall_score", 0) > 0 and not e.get("is_error")]

    # ── Per-dimension scores ─────────────────────────────────────
    def avg(field):
        vals = [e.get(field, 0) for e in scored if e.get(field, 0) > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    communication_score = avg("clarity")
    leadership_score = avg("leadership")
    problem_solving_score = avg("ownership")
    technical_score = avg("result_orientation")

    # ── Weighted score ───────────────────────────────────────────
    weighted_scores = [s for _, s in context.weighted_score_history]
    avg_weighted = (
        round(sum(weighted_scores) / len(weighted_scores), 2)
        if weighted_scores else 0.0
    )

    # ── Strengths & Weaknesses aggregation ───────────────────────
    all_strengths = []
    all_weaknesses = []
    for e in scored:
        all_strengths.extend(e.get("strengths", []))
        all_weaknesses.extend(e.get("weaknesses", []))

    # Deduplicate and take top items
    strengths = list(dict.fromkeys(all_strengths))[:5]
    weaknesses = list(dict.fromkeys(all_weaknesses))[:5]

    # ── Candidate summary ────────────────────────────────────────
    total_turns = context.turn_count
    skills_str = ", ".join(context.skills) if context.skills else "general"
    candidate_summary = (
        f"Candidate assessed over {total_turns} turns. "
        f"Skills: {skills_str}. "
        f"Average weighted score: {avg_weighted}/5.0. "
        f"Trend: {trend_label}. Consistency: {consistency_rating}."
    )

    # ── Hire recommendation ──────────────────────────────────────
    hire_recommendation = derive_hire_recommendation(
        avg_weighted, consistency_rating, trend_label
    )

    # ── Risk flags ───────────────────────────────────────────────
    risk_flags = _compute_risk_flags(
        avg_weighted, consistency_rating, trend_label, scored, context
    )

    return {
        "candidate_summary": candidate_summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "communication_score": communication_score,
        "leadership_score": leadership_score,
        "problem_solving_score": problem_solving_score,
        "technical_score": technical_score,
        "consistency_rating": consistency_rating,
        "trend_label": trend_label,
        "hire_recommendation": hire_recommendation,
        "risk_flags": risk_flags,
    }


def derive_hire_recommendation(
    weighted_score: float,
    consistency_rating: str,
    trend_label: str,
) -> str:
    """
    Derive a hire recommendation from aggregate metrics.

    Returns:
        One of: STRONG_HIRE, HIRE, LEAN_HIRE, NO_HIRE
    """
    # Base score tiers
    if weighted_score >= 4.0:
        base = "STRONG_HIRE"
    elif weighted_score >= 3.0:
        base = "HIRE"
    elif weighted_score >= 2.0:
        base = "LEAN_HIRE"
    else:
        base = "NO_HIRE"

    # Modifiers: consistency and trend can adjust the recommendation
    # Downgrade if consistency is Low
    if consistency_rating == "Low" and base in ("STRONG_HIRE", "HIRE"):
        base = _downgrade(base)

    # Downgrade if trend is declining
    if trend_label == "declining" and base in ("STRONG_HIRE", "HIRE"):
        base = _downgrade(base)

    # Upgrade if trend is improving and consistency is High
    if trend_label == "improving" and consistency_rating == "High":
        if base in ("LEAN_HIRE", "HIRE"):
            base = _upgrade(base)

    return base


def generate_candidate_summary(dm) -> dict:
    """
    Generate a compact candidate summary for the /sessions/{id}/summary endpoint.

    Args:
        dm: DialogueManager instance

    Returns:
        Compact summary dict.
    """
    context = dm.context
    eval_summary = context.get_evaluation_summary()

    weighted_scores = [s for _, s in context.weighted_score_history]
    avg_weighted = (
        round(sum(weighted_scores) / len(weighted_scores), 2)
        if weighted_scores else 0.0
    )

    return {
        "session_id": dm.session_id,
        "total_turns": context.turn_count,
        "skills": context.skills,
        "avg_weighted_score": avg_weighted,
        "final_hire_signal": (
            eval_summary.get("final_hire_signal", "N/A")
            if eval_summary else "N/A"
        ),
    }


def rank_candidates(session_data_list: list) -> list:
    """
    Rank candidates by composite criteria.

    Sorting priority:
        1. weighted_score (descending)
        2. consistency_rating (High > Moderate > Low > N/A)
        3. improving trend preferred

    Args:
        session_data_list: list of dicts with keys:
            session_id, final_weighted_score, consistency_rating,
            trend_label, hire_recommendation

    Returns:
        Sorted list (best candidate first).
    """
    consistency_order = {"High": 3, "Moderate": 2, "Low": 1, "N/A": 0}
    trend_order = {"improving": 2, "stable": 1, "declining": 0,
                   "insufficient_data": 0}

    def sort_key(item):
        return (
            item.get("final_weighted_score", 0),
            consistency_order.get(item.get("consistency_rating", "N/A"), 0),
            trend_order.get(item.get("trend_label", "stable"), 0),
        )

    return sorted(session_data_list, key=sort_key, reverse=True)


# ── Private helpers ──────────────────────────────────────────────

def _downgrade(recommendation: str) -> str:
    """Downgrade a hire recommendation by one tier."""
    order = ["STRONG_HIRE", "HIRE", "LEAN_HIRE", "NO_HIRE"]
    idx = order.index(recommendation) if recommendation in order else 1
    return order[min(idx + 1, len(order) - 1)]


def _upgrade(recommendation: str) -> str:
    """Upgrade a hire recommendation by one tier."""
    order = ["STRONG_HIRE", "HIRE", "LEAN_HIRE", "NO_HIRE"]
    idx = order.index(recommendation) if recommendation in order else 2
    return order[max(idx - 1, 0)]


def _compute_risk_flags(
    avg_weighted: float,
    consistency_rating: str,
    trend_label: str,
    scored: list,
    context,
) -> list:
    """Identify risk flags for the recruiter report."""
    flags = []

    if consistency_rating == "Low":
        flags.append("Inconsistent performance across interview turns")

    if trend_label == "declining":
        flags.append("Declining performance trend during interview")

    if avg_weighted < 2.0:
        flags.append("Overall score critically low")

    # Check for missing STAR results
    missing_results = context.star_stats.get("missing_result_count", 0)
    total_star = len([e for e in scored if "star_breakdown" in e])
    if total_star > 0 and missing_results / total_star > 0.5:
        flags.append("Frequently missing measurable results in STAR responses")

    # Check for any dimension consistently below 2
    for dim in ["clarity", "structure", "confidence", "ownership",
                "leadership", "result_orientation"]:
        vals = [e.get(dim, 0) for e in scored if e.get(dim, 0) > 0]
        if vals and (sum(vals) / len(vals)) < 2.0:
            flags.append(f"Consistently weak in {dim}")

    return flags
