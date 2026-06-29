"""
Follow-up policy — maps evaluation signals to explicit follow-up types.

Aligned with LLM-as-Interviewer research taxonomy:
rationale, elaboration, clarification, advance.
"""

from __future__ import annotations

FOLLOWUP_RATIONALE = "rationale"
FOLLOWUP_ELABORATION = "elaboration"
FOLLOWUP_CLARIFICATION = "clarification"
FOLLOWUP_ADVANCE = "advance"


def classify_followup_type(
    evaluation: dict,
    decision: dict,
    *,
    domain: str = "",
    answer_word_count: int = 0,
    engine_reason: str = "",
) -> tuple[str, str]:
    """
    Classify the follow-up type and human-readable reason.

    Returns:
        (followup_type, followup_reason)
    """
    decision_type = (decision or {}).get("type", "ADVANCE")
    weakest = (evaluation or {}).get("weakest_dimension", "")
    weighted = (evaluation or {}).get(
        "weighted_overall_score", (evaluation or {}).get("overall_score", 0)
    )

    if decision_type == "ADVANCE" or engine_reason in {
        "probe_limit_reached_moving_to_next_domain",
        "all_domains_complete",
        "context_followup_after_good_answer",
    }:
        if engine_reason == "context_followup_after_good_answer":
            return (
                FOLLOWUP_ELABORATION,
                "Strong answer warranted a context-aware elaboration follow-up.",
            )
        return FOLLOWUP_ADVANCE, "Answer sufficient; advancing to the next interview topic."

    if answer_word_count < 8 or weighted <= 2.0:
        return (
            FOLLOWUP_CLARIFICATION,
            "Answer was too short or vague; clarification follow-up requested.",
        )

    rationale_dimensions = {"clarity", "structure", "confidence"}
    if weakest in rationale_dimensions:
        return (
            FOLLOWUP_RATIONALE,
            f"Answer needed clearer reasoning ({weakest}); rationale follow-up requested.",
        )

    return (
        FOLLOWUP_ELABORATION,
        f"Answer needed more depth on {weakest or 'technical detail'}; elaboration follow-up requested.",
    )


def build_followup_label(followup_type: str) -> str:
    """Readable label for reports."""
    labels = {
        FOLLOWUP_RATIONALE: "Rationale probe",
        FOLLOWUP_ELABORATION: "Elaboration probe",
        FOLLOWUP_CLARIFICATION: "Clarification probe",
        FOLLOWUP_ADVANCE: "Advance to next domain",
    }
    return labels.get(followup_type, followup_type)
