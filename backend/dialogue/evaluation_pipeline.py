"""
Evaluation pipeline — orchestrates primary scoring, optional rethink ensemble, and follow-up decision.

Phase 4: separates scoring reliability (ensemble) from turn decision while preserving
the adaptive_evaluate() response contract for DialogueManager.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from evaluation.rubric import (
    apply_transcript_quality_adjustment,
    compute_profile_scores,
    get_evaluation_methodology,
    merge_evaluations,
    should_trigger_rethink,
)

if TYPE_CHECKING:
    from dialogue.evaluator import Evaluator

logger = logging.getLogger(__name__)


class EvaluationPipeline:
    """
    Lite ensemble evaluation pipeline (SWE-Judge inspired).

    Flow:
        1. Primary adaptive call (score + follow-up decision)
        2. Optional rethink pass when score is borderline
        3. Merge scores conservatively; decision from primary pass
    """

    def __init__(self, evaluator: "Evaluator"):
        self._evaluator = evaluator

    def evaluate_turn(
        self,
        question: str,
        answer: str,
        previous_evaluations: list,
        interview_stage: str,
        domain: str = "",
        transcript_quality: dict | None = None,
    ) -> dict[str, Any]:
        """
        Run full evaluation for one candidate turn.

        Returns same shape as legacy adaptive_evaluate():
            evaluation, decision, latency_ms, evaluation_method
        """
        total_latency = 0.0
        rethink_applied = False

        primary = self._evaluator._run_primary_adaptive(
            question=question,
            answer=answer,
            previous_evaluations=previous_evaluations,
            interview_stage=interview_stage,
            transcript_quality=transcript_quality,
        )
        total_latency += primary.get("latency_ms", 0)

        evaluation = primary.get("evaluation", {})
        decision = primary.get("decision", {})

        evaluation = apply_transcript_quality_adjustment(evaluation, transcript_quality)
        if evaluation and "score_profiles" not in evaluation:
            evaluation["score_profiles"] = compute_profile_scores(evaluation)

        if should_trigger_rethink(evaluation):
            rethink_result = self._evaluator.rethink_evaluation(
                question=question,
                answer=answer,
                primary_evaluation=evaluation,
                domain=domain,
            )
            total_latency += rethink_result.get("latency_ms", 0)
            if rethink_result.get("evaluation"):
                evaluation = merge_evaluations(evaluation, rethink_result["evaluation"])
                evaluation = apply_transcript_quality_adjustment(
                    evaluation, transcript_quality
                )
                evaluation["score_profiles"] = compute_profile_scores(evaluation)
                rethink_applied = True
                logger.debug(
                    "Rethink ensemble applied: primary=%.2f merged=%.2f",
                    primary["evaluation"].get("weighted_overall_score", 0),
                    evaluation.get("weighted_overall_score", 0),
                )

        method = get_evaluation_methodology()
        method["primary_pass"] = True
        method["rethink_applied"] = rethink_applied
        method["total_latency_ms"] = round(total_latency, 2)
        if transcript_quality:
            method["transcript_quality"] = transcript_quality

        return {
            "evaluation": evaluation,
            "decision": decision,
            "latency_ms": round(total_latency, 2),
            "evaluation_method": method,
        }

    def score_answer_only(self, question: str, answer: str, domain: str = "") -> dict[str, Any]:
        """Score without follow-up decision — for export / offline analysis."""
        return self._evaluator.score_answer(question, answer, domain=domain)
