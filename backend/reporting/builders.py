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
    """
    Build recruiter Q&A history from the adaptive trace.

    Includes scored turns plus unscored/error and meaningful redirect turns so
    the HTML report matches what was spoken (not only successfully scored).
    """
    include_redirects = {
        "IDK_RESPONSE",
        "TAIL_FRAGMENT_CONTINUE",
        "REPEAT_REQUEST",
        "STAY_ON_QUESTION",
        "INCOMPLETE_TRANSCRIPT_REDIRECT",
        "SKIP_BUDGET_EXCEEDED",
    }
    exclude_noise = {
        "DOMAIN_RELEVANCE_REDIRECT",
        "META_CONVERSATION",
        "SKIP_REQUEST",
        "OFF_TOPIC",
        "EXTERNAL_PROMPT_ECHO",
    }

    reviews = []
    for item in adaptive_trace or []:
        decision_type = item.get("decision_type") or ""
        guard_passed = item.get("guard_passed", True)

        if decision_type in exclude_noise:
            continue
        if not guard_passed and decision_type not in include_redirects:
            continue

        scores = item.get("scores") or {}
        profiles = item.get("score_profiles") or {}
        comm = profiles.get("communication", {}).get("composite")
        tech = profiles.get("technical", {}).get("composite")
        weighted = scores.get("weighted_overall_score", 0) or 0
        is_error = bool(item.get("is_error") or scores.get("is_error"))
        has_score = (weighted > 0) or bool(comm) or bool(tech)

        question = (item.get("question_answered") or item.get("next_question") or "").strip()
        if not question:
            continue
        # Skip placeholder error prompts that never asked a real domain question
        if question.startswith("[Error generating") and not has_score:
            # Still include if candidate answered something meaningful against it
            answer_probe = (item.get("candidate_answer") or "").strip()
            if len(answer_probe.split()) < 3 and decision_type not in include_redirects:
                continue

        answer = (item.get("candidate_answer") or "").strip()
        if len(answer) > 280:
            answer = answer[:277] + "..."

        if has_score and not is_error:
            review_status = "scored"
            evaluation_summary = _brief_evaluation_summary(item, float(weighted))
            score_block = {
                "communication_composite": comm,
                "technical_composite": tech,
                "weighted_overall": weighted,
            }
            hire_signal = item.get("hire_signal")
        elif has_score and (is_error or item.get("evaluation_degraded")):
            review_status = "scored_degraded"
            evaluation_summary = (
                f"Weighted score {float(weighted):.2f} (evaluation degraded). "
                "Scoring failed; conservative floor applied."
            )
            score_block = {
                "communication_composite": comm,
                "technical_composite": tech,
                "weighted_overall": weighted,
            }
            hire_signal = item.get("hire_signal") or "No Hire"
        elif is_error or (guard_passed and not has_score):
            review_status = "evaluation_unavailable"
            evaluation_summary = (
                "Evaluation unavailable for this turn "
                "(scoring failed or returned no usable score)."
            )
            score_block = {
                "communication_composite": None,
                "technical_composite": None,
                "weighted_overall": None,
            }
            hire_signal = "N/A"
        else:
            review_status = "redirect"
            evaluation_summary = (
                f"Not scored ({decision_type.replace('_', ' ').title()}). "
                "Interviewer redirected or asked the candidate to continue."
            )
            score_block = {
                "communication_composite": None,
                "technical_composite": None,
                "weighted_overall": None,
            }
            hire_signal = "N/A"

        reviews.append(
            {
                "turn": item.get("turn"),
                "domain": item.get("domain"),
                "domain_label": DOMAIN_LABELS.get(
                    item.get("domain", ""),
                    str(item.get("domain", "")).replace("_", " ").title(),
                ),
                "question": question,
                "candidate_answer_summary": answer,
                "evaluation_summary": evaluation_summary,
                "review_status": review_status,
                "scores": score_block,
                "hire_signal_per_turn": hire_signal,
            }
        )
    return reviews


def _brief_evaluation_summary(item: dict, weighted: float) -> str:
    weakest = item.get("weakest_dimension")
    signal = item.get("hire_signal", "N/A")
    parts = [f"Weighted score {weighted:.2f} ({signal})."]
    if weakest and weakest != "unknown":
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
