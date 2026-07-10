"""Build recruiter-facing sections from legacy analytics."""

from __future__ import annotations

from reporting.completion_policy import count_evaluated_turns
from reporting.schema import DOMAIN_LABELS, PARTIAL_RECOMMENDATION_RATIONALE


def _rating_label(score: float | None) -> str:
    if score is None:
        return "N/A"
    if score >= 4.0:
        return "Strong"
    if score >= 3.0:
        return "Adequate"
    if score >= 2.0:
        return "Developing"
    return "Weak"


def _domain_status_to_rating(status: str) -> tuple[str, str]:
    status = (status or "").lower()
    if status.startswith("covered_strong"):
        return "Strong", "assessed"
    if status.startswith("covered"):
        return "Adequate", "assessed"
    if status == "visited_unscored":
        return "N/A", "partially_assessed"
    if status == "not_assessed":
        return "N/A", "not_reached"
    return "N/A", "skipped"


def build_domain_ratings(domain_assessment_map: dict) -> list[dict]:
    ratings = []
    for domain_id, info in (domain_assessment_map or {}).items():
        status = info.get("status", "not_assessed")
        rating, assessment_status = _domain_status_to_rating(status)
        ratings.append(
            {
                "domain_id": domain_id,
                "domain_label": DOMAIN_LABELS.get(
                    domain_id, domain_id.replace("_", " ").title()
                ),
                "status": assessment_status,
                "rating": rating,
                "evidence_turns": info.get("coverage_turns", []),
                "brief_note": info.get("reason", ""),
            }
        )
    return ratings


def build_question_review(adaptive_trace: list) -> list[dict]:
    reviews = []
    for item in adaptive_trace or []:
        if not item.get("guard_passed", True):
            continue
        if item.get("decision_type") in {
            "DOMAIN_RELEVANCE_REDIRECT",
            "INCOMPLETE_TRANSCRIPT_REDIRECT",
            "META_CONVERSATION",
            "SKIP_REQUEST",
        }:
            continue
        scores = item.get("scores") or {}
        profiles = item.get("score_profiles") or {}
        comm = profiles.get("communication", {}).get("composite")
        tech = profiles.get("technical", {}).get("composite")
        weighted = scores.get("weighted_overall_score", 0)
        if weighted <= 0 and not comm and not tech:
            continue

        answer = (item.get("candidate_answer") or "").strip()
        if len(answer) > 280:
            answer = answer[:277] + "..."

        reviews.append(
            {
                "turn": item.get("turn"),
                "domain": item.get("domain"),
                "domain_label": DOMAIN_LABELS.get(
                    item.get("domain", ""),
                    str(item.get("domain", "")).replace("_", " ").title(),
                ),
                "question": item.get("question_answered") or item.get("next_question"),
                "candidate_answer_summary": answer,
                "evaluation_summary": _brief_evaluation_summary(item, weighted),
                "scores": {
                    "communication_composite": comm,
                    "technical_composite": tech,
                    "weighted_overall": weighted,
                },
                "hire_signal_per_turn": item.get("hire_signal"),
            }
        )
    return reviews


def _brief_evaluation_summary(item: dict, weighted: float) -> str:
    weakest = item.get("weakest_dimension")
    signal = item.get("hire_signal", "N/A")
    parts = [f"Weighted score {weighted:.2f} ({signal})."]
    if weakest:
        parts.append(f"Weakest dimension: {weakest}.")
    reason = item.get("follow_up_reason")
    if reason and "advancing" not in str(reason).lower():
        parts.append(str(reason))
    return " ".join(parts)


def build_ratings_summary(legacy: dict, report_type: str, evaluated_turns: int) -> dict:
    ws = legacy.get("weighted_score_summary", {}) or {}
    profiles = legacy.get("score_profile_summary", {}) or {}
    comm = profiles.get("communication", {})
    tech = profiles.get("technical", {})

    overall_score = ws.get("avg_weighted_overall", 0)
    comm_score = comm.get("composite", 0)
    tech_score = tech.get("composite", 0)
    confidence_score = ws.get("avg_confidence", 0)

    confidence_rating = {
        "score": confidence_score,
        "label": _rating_label(confidence_score) if evaluated_turns >= 2 else "N/A",
        "confidence": "moderate" if evaluated_turns >= 3 else "low",
    }
    if evaluated_turns < 2:
        confidence_rating["note"] = "Insufficient evidence for confidence assessment."

    recommendation = _build_final_recommendation(ws, report_type)

    return {
        "overall_performance": {
            "score": overall_score,
            "label": _rating_label(overall_score) if evaluated_turns else "N/A",
            "confidence": "high" if report_type == "complete" else "low",
        },
        "technical_performance": {
            "score": tech_score,
            "label": _rating_label(tech_score) if evaluated_turns else "N/A",
        },
        "communication_skills": {
            "score": comm_score,
            "label": _rating_label(comm_score) if evaluated_turns else "N/A",
        },
        "confidence_professionalism": confidence_rating,
        "final_recommendation": recommendation,
    }


def _build_final_recommendation(ws: dict, report_type: str) -> dict:
    if report_type in ("partial", "incomplete", "aborted"):
        return {
            "signal": "N/A",
            "rationale": PARTIAL_RECOMMENDATION_RATIONALE
            if report_type == "partial"
            else (
                "Insufficient assessed data. No hiring signal is provided for this session."
            ),
            "confidence": "none",
            "disclaimer": (
                "This is a decision-support signal only, not a final hiring decision."
            ),
        }

    signal = ws.get("final_hire_signal", "N/A")
    avg = ws.get("avg_weighted_overall", 0)
    return {
        "signal": signal,
        "rationale": (
            f"Based on {ws.get('total_evaluated', 0)} evaluated turns with an average "
            f"weighted score of {avg}."
        ),
        "confidence": "moderate",
        "disclaimer": (
            "This is a decision-support signal only, not a final hiring decision."
        ),
    }


def build_strengths_and_improvements(legacy: dict) -> tuple[list[str], list[str]]:
    recruiter = legacy.get("recruiter_summary", {}) or {}
    strengths = list(recruiter.get("main_strengths", []) or [])[:5]
    concerns = list(recruiter.get("main_concerns", []) or [])[:5]
    followups = list(recruiter.get("recommended_follow_up_areas", []) or [])[:3]
    improvements = concerns + [f for f in followups if f not in concerns]
    return strengths, improvements[:8]
