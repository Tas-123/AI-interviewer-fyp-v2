"""
Evaluator — LLM-based answer evaluation using a 6-criterion scoring rubric.

Phase 4: EvaluationPipeline orchestrates primary scoring + optional rethink ensemble.
Public API:
  - adaptive_evaluate() — full turn (score + decision) via pipeline
  - score_answer()       — scoring only
  - rethink_evaluation() — second-pass scoring
  - evaluate()           — legacy standalone scoring
"""

import json
import logging
import os
import time
from dotenv import load_dotenv
from groq import Groq
from core.config import settings
from dialogue.prompts import (
    EVALUATION_SYSTEM_PROMPT,
    WEAKNESS_FOLLOWUP_PROMPT,
    ADAPTIVE_EVALUATION_PROMPT,
    RETHINK_EVALUATION_PROMPT,
)
from evaluation.rubric import compute_weighted_score, derive_hire_signal

logger = logging.getLogger(__name__)


def load_groq_client():
    """Load Groq client from environment."""
    load_dotenv()
    api_key = settings.groq_api_key
    if not api_key:
        raise ValueError("GROQ_API_KEY not found.")
    return Groq(api_key=api_key)


class Evaluator:

    def __init__(self):
        self.client = load_groq_client()
        self.model = settings.groq_evaluator_model or settings.groq_model
        self._pipeline = None

    @property
    def pipeline(self):
        if self._pipeline is None:
            from dialogue.evaluation_pipeline import EvaluationPipeline
            self._pipeline = EvaluationPipeline(self)
        return self._pipeline

    def _call_groq(self, prompt: str, json_mode: bool = False) -> str:
        """Call Groq and return raw text."""
        from dialogue.groq_debug_log import log_groq_exchange

        log_groq_exchange("GROQ_EVAL_PROMPT", prompt)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a fair senior engineer evaluating Junior AI Engineer "
                    "candidates in a live voice interview. "
                    "Return only valid JSON when JSON is requested. "
                    "No markdown, no code fences, no extra commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 700 if json_mode else 220,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content.strip()
        log_groq_exchange("GROQ_EVAL_REPLY", text)
        return text

    # ════════════════════════════════════════════════════════════
    #  Phase 4 — Public evaluation API
    # ════════════════════════════════════════════════════════════

    def adaptive_evaluate(
        self,
        question: str,
        answer: str,
        previous_evaluations: list,
        interview_stage: str,
        domain: str = "",
        transcript_quality: dict | None = None,
        recent_qa_memory: str = "",
    ) -> dict:
        """
        Evaluate answer and decide next question via EvaluationPipeline.

        Returns:
            evaluation, decision, latency_ms, evaluation_method
        """
        if not answer or len(answer.strip().split()) < 3:
            return {
                "evaluation": self._empty_evaluation(),
                "decision": {
                    "type": "PROBE",
                    "next_question": (
                        "I caught only a very short answer. Please answer the current "
                        "question directly with concrete technical steps, tools, reasoning, "
                        "and how you would validate your approach."
                    ),
                },
                "latency_ms": 0,
                "evaluation_method": {"rethink_applied": False, "primary_pass": False},
            }

        return self.pipeline.evaluate_turn(
            question=question,
            answer=answer,
            previous_evaluations=previous_evaluations,
            interview_stage=interview_stage,
            domain=domain,
            transcript_quality=transcript_quality,
            recent_qa_memory=recent_qa_memory,
        )

    def score_answer(self, question: str, answer: str, domain: str = "") -> dict:
        """Score an answer without generating a follow-up decision."""
        if not answer or len(answer.strip().split()) < 3:
            return self._empty_evaluation()

        raw = self.evaluate(question, answer)
        return self._legacy_to_adaptive_format(raw)

    def rethink_evaluation(
        self,
        question: str,
        answer: str,
        primary_evaluation: dict,
        domain: str = "",
    ) -> dict:
        """Second-pass scoring for borderline evaluations (ensemble lite)."""
        prompt = RETHINK_EVALUATION_PROMPT.format(
            question=question,
            answer=answer,
            primary_evaluation=json.dumps(primary_evaluation, ensure_ascii=False),
        )

        t_start = time.perf_counter()
        try:
            raw_text = self._parse_json_response(self._call_groq(prompt, json_mode=True))
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            evaluation = self._validate_adaptive_evaluation(raw_text)
            return {"evaluation": evaluation, "latency_ms": latency_ms}
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.warning("Rethink error: %s", exc)
            return {"evaluation": None, "latency_ms": latency_ms}

    def _run_primary_adaptive(
        self,
        question: str,
        answer: str,
        previous_evaluations: list,
        interview_stage: str,
        transcript_quality: dict | None = None,
        recent_qa_memory: str = "",
    ) -> dict:
        """Primary adaptive LLM call — scores answer and suggests follow-up."""
        quality_note = ""
        if transcript_quality and transcript_quality.get("is_noisy"):
            quality_note = (
                "\n\nSTT quality note: The candidate answer may contain speech-to-text "
                "repetition or fragmentation. Score technical intent and ownership generously. "
                "Do not heavily penalize clarity or structure if repetition artifacts are present."
            )

        memory_note = ""
        if (recent_qa_memory or "").strip():
            memory_note = (
                f"\n\n{recent_qa_memory.strip()}\n"
                "If you choose PROBE, you may briefly reference a concrete detail from "
                "prior answers when it helps continuity."
            )

        prompt = ADAPTIVE_EVALUATION_PROMPT.format(
            current_question=question,
            candidate_answer=answer,
            previous_evaluations=json.dumps(previous_evaluations),
            interview_stage=interview_stage,
        ) + quality_note + memory_note

        t_start = time.perf_counter()
        try:
            raw_text = self._call_groq(prompt, json_mode=True)
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            result = self._parse_json_response(raw_text)
            result["evaluation"] = self._validate_adaptive_evaluation(
                result.get("evaluation", {})
            )
            result["decision"] = self._validate_decision(result.get("decision", {}))
            result["latency_ms"] = latency_ms
            return result

        except json.JSONDecodeError as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.warning("Adaptive JSON parse error: %s", exc)
            fallback = self._fallback_adaptive_result()
            fallback["latency_ms"] = latency_ms
            return fallback

        except Exception as exc:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.warning("Adaptive error: %s", exc)
            fallback = self._fallback_adaptive_result()
            fallback["latency_ms"] = latency_ms
            return fallback

    # ════════════════════════════════════════════════════════════
    #  Legacy Evaluation
    # ════════════════════════════════════════════════════════════

    def evaluate(self, question: str, answer: str) -> dict:
        """Legacy standalone evaluation (no follow-up decision)."""
        if not answer or len(answer.strip().split()) < 3:
            return self._empty_evaluation()

        prompt = EVALUATION_SYSTEM_PROMPT.format(question=question, answer=answer)

        try:
            raw_text = self._call_groq(prompt, json_mode=True)
            evaluation = self._parse_json_response(raw_text)
            return self._validate_evaluation(evaluation)

        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error: %s", exc)
            return self._error_evaluation("Failed to parse LLM evaluation response.")

        except Exception as exc:
            logger.warning("Evaluation error: %s", exc)
            return self._error_evaluation(str(exc))

    def generate_weakness_followup(
        self, question: str, answer: str, weaknesses: list
    ) -> str | None:
        """Generate a follow-up question targeting identified weaknesses."""
        if not weaknesses:
            return None

        weaknesses_text = "\n".join(f"- {w}" for w in weaknesses)
        prompt = WEAKNESS_FOLLOWUP_PROMPT.format(
            weaknesses=weaknesses_text,
            question=question,
            answer=answer,
        )

        try:
            return self._call_groq(prompt, json_mode=False)
        except Exception as exc:
            logger.warning("Follow-up generation error: %s", exc)
            return None

    # ════════════════════════════════════════════════════════════
    #  Validation Helpers
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _parse_json_response(raw_text: str) -> dict:
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            raw_text = raw_text.rsplit("```", 1)[0]
            raw_text = raw_text.strip()
        return json.loads(raw_text)

    def _legacy_to_adaptive_format(self, data: dict) -> dict:
        """Convert legacy evaluate() output to adaptive evaluation shape."""
        return self._validate_adaptive_evaluation({
            "clarity": data.get("clarity", data.get("clarity_score", 0)),
            "structure": data.get("structure", data.get("structure_score", 0)),
            "confidence": data.get("confidence", data.get("confidence_score", 0)),
            "ownership": data.get("ownership", data.get("ownership_score", 0)),
            "leadership": data.get("leadership", data.get("leadership_score", 0)),
            "result_orientation": data.get(
                "result_orientation", data.get("result_score", 0)
            ),
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "star_breakdown": data.get("star_breakdown", {}),
        })

    def _validate_adaptive_evaluation(self, data: dict) -> dict:
        """Validate the evaluation block from adaptive response."""
        score_fields = [
            "clarity", "structure", "confidence",
            "ownership", "leadership", "result_orientation",
        ]

        for field in score_fields:
            val = data.get(field, 0)
            try:
                val = float(val)
            except Exception:
                val = 1.0
            data[field] = round(max(1.0, min(5.0, val)), 2)

        scores = [data[f] for f in score_fields]
        data["overall_score"] = round(sum(scores) / len(scores), 2)
        data["weighted_overall_score"] = compute_weighted_score(data)

        min_score = min(scores)
        data["weakest_dimension"] = score_fields[scores.index(min_score)]

        valid_signals = ["Strong Hire", "Hire", "Borderline", "No Hire"]
        if data.get("hire_signal") not in valid_signals:
            data["hire_signal"] = derive_hire_signal(data["weighted_overall_score"])

        star = data.get("star_breakdown", {})
        data["star_breakdown"] = {
            "situation_present": bool(star.get("situation_present", False)),
            "task_present": bool(star.get("task_present", False)),
            "action_present": bool(star.get("action_present", False)),
            "result_present": bool(star.get("result_present", False)),
        }

        data.setdefault("strengths", [])
        data.setdefault("weaknesses", [])

        return data

    def _validate_decision(self, data: dict) -> dict:
        """Validate the decision block from adaptive response."""
        if data.get("type") not in ("PROBE", "ADVANCE"):
            data["type"] = "ADVANCE"
        if not data.get("next_question"):
            data["next_question"] = (
                "Can you share one specific project where you ran into a tough technical problem?"
            )
        return data

    def _validate_evaluation(self, data: dict) -> dict:
        """Ensure all expected fields exist and are in valid range (legacy format)."""
        score_fields = [
            "clarity_score", "structure_score", "confidence_score",
            "ownership_score", "leadership_score", "result_score",
        ]

        for field in score_fields:
            val = data.get(field, 0)
            try:
                val = float(val)
            except Exception:
                val = 1.0
            data[field] = round(max(1.0, min(5.0, val)), 2)

        scores = [data[f] for f in score_fields]
        data["overall_score"] = round(sum(scores) / len(scores), 2)

        data["clarity"] = data["clarity_score"]
        data["structure"] = data["structure_score"]
        data["confidence"] = data["confidence_score"]
        data["ownership"] = data["ownership_score"]
        data["leadership"] = data["leadership_score"]
        data["result_orientation"] = data["result_score"]

        data["weighted_overall_score"] = compute_weighted_score(data)

        dimension_names = [
            "clarity", "structure", "confidence",
            "ownership", "leadership", "result_orientation",
        ]
        min_score = min(scores)
        min_idx = scores.index(min_score)
        data["weakest_dimension"] = dimension_names[min_idx]

        valid_signals = ["Strong Hire", "Hire", "Borderline", "No Hire"]
        if data.get("hire_signal") not in valid_signals:
            data["hire_signal"] = derive_hire_signal(data["weighted_overall_score"])

        data.setdefault("strengths", [])
        data.setdefault("weaknesses", [])

        return data

    def _empty_evaluation(self) -> dict:
        """Return a default evaluation for empty/trivial answers."""
        base = {
            "clarity": 1, "structure": 1, "confidence": 1,
            "ownership": 1, "leadership": 1, "result_orientation": 1,
        }
        return {
            **base,
            "clarity_score": 1, "structure_score": 1, "confidence_score": 1,
            "ownership_score": 1, "leadership_score": 1, "result_score": 1,
            "strengths": [],
            "weaknesses": ["Answer too short or empty to evaluate."],
            "overall_score": 1.0,
            "weighted_overall_score": compute_weighted_score(base),
            "weakest_dimension": "clarity",
            "hire_signal": "No Hire",
        }

    def _error_evaluation(self, error_msg: str) -> dict:
        """Return a placeholder evaluation when LLM call fails."""
        return {
            "clarity_score": 0, "clarity": 0,
            "structure_score": 0, "structure": 0,
            "confidence_score": 0, "confidence": 0,
            "ownership_score": 0, "ownership": 0,
            "leadership_score": 0, "leadership": 0,
            "result_score": 0, "result_orientation": 0,
            "strengths": [],
            "weaknesses": [f"Evaluation error: {error_msg}"],
            "overall_score": 0.0,
            "weighted_overall_score": 0.0,
            "weakest_dimension": "unknown",
            "hire_signal": "N/A",
            "is_error": True,
        }

    def _fallback_adaptive_result(self) -> dict:
        """Return a safe fallback when adaptive evaluation fails entirely."""
        return {
            "evaluation": self._error_evaluation("Adaptive evaluation failed."),
            "decision": {
                "type": "ADVANCE",
                "next_question": (
                    "Let's make this concrete. Please explain one practical technical "
                    "approach you would take, including the steps, tools, trade-offs, "
                    "and how you would validate it."
                ),
            },
        }
