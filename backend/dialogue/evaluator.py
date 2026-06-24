"""
Evaluator — LLM-based answer evaluation using a 6-criterion scoring rubric.
Includes adaptive evaluation that scores AND decides the next question in one call.
"""

import json
import os
import time
from dotenv import load_dotenv
from groq import Groq
from dialogue.prompts import (
    EVALUATION_SYSTEM_PROMPT,
    WEAKNESS_FOLLOWUP_PROMPT,
    ADAPTIVE_EVALUATION_PROMPT,
)
from dialogue.analytics import compute_weighted_score


def load_groq_client():
    """Load Groq client from environment."""
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found.")
    return Groq(api_key=api_key)


class Evaluator:

    def __init__(self):
        self.client = load_groq_client()
        self.model = os.getenv("GROQ_EVALUATOR_MODEL", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))

    def _call_groq(self, prompt: str, json_mode: bool = False) -> str:
        """Call Groq and return raw text."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict senior HR interviewer and evaluator. "
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
        return response.choices[0].message.content.strip()

    # ════════════════════════════════════════════════════════════
    #  Adaptive Evaluation (PROBE / ADVANCE)
    # ════════════════════════════════════════════════════════════

    def adaptive_evaluate(
        self,
        question: str,
        answer: str,
        previous_evaluations: list,
        interview_stage: str,
    ) -> dict:
        """
        Single LLM call that:
        1. Scores the candidate's answer on 6 dimensions
        2. Identifies the weakest dimension
        3. Decides PROBE (follow-up on weakness) or ADVANCE (new topic)
        4. Generates the next question

        Returns:
            {
                "evaluation": { clarity, structure, confidence, ownership,
                                leadership, result_orientation, overall_score,
                                weakest_dimension, hire_signal },
                "decision": { type: "PROBE"|"ADVANCE", next_question: "" }
            }
        """
        if not answer or len(answer.strip().split()) < 3:
            return {
                "evaluation": self._empty_evaluation(),
                "decision": {
                    "type": "PROBE",
                    "next_question": "I caught only a very short answer. Please answer the current question directly with concrete technical steps, tools, reasoning, and how you would validate your approach.",
                },
                "latency_ms": 0,
            }

        prompt = ADAPTIVE_EVALUATION_PROMPT.format(
            current_question=question,
            candidate_answer=answer,
            previous_evaluations=json.dumps(previous_evaluations),
            interview_stage=interview_stage,
        )

        t_start = time.perf_counter()
        try:
            
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            raw_text = self._call_groq(prompt, json_mode=True)
            

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                raw_text = raw_text.rsplit("```", 1)[0]
                raw_text = raw_text.strip()

            result = json.loads(raw_text)
            result["evaluation"] = self._validate_adaptive_evaluation(
                result.get("evaluation", {})
            )
            result["decision"] = self._validate_decision(
                result.get("decision", {})
            )
            result["latency_ms"] = latency_ms
            return result

        except json.JSONDecodeError as e:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            print(f"[Evaluator] Adaptive JSON parse error: {e}")
            print(f"[Evaluator] Raw response: {raw_text}")
            fallback = self._fallback_adaptive_result()
            fallback["latency_ms"] = latency_ms
            return fallback

        except Exception as e:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            print(f"[Evaluator] Adaptive error: {e}")
            fallback = self._fallback_adaptive_result()
            fallback["latency_ms"] = latency_ms
            return fallback

    # ════════════════════════════════════════════════════════════
    #  Legacy Evaluation (kept for backward compatibility)
    # ════════════════════════════════════════════════════════════

    def evaluate(self, question: str, answer: str) -> dict:
        """
        Evaluate a candidate's answer against the given question.
        Returns a dict with 6 scores, strengths, weaknesses,
        overall_score, and hire_signal.
        """
        if not answer or len(answer.strip().split()) < 3:
            return self._empty_evaluation()

        prompt = EVALUATION_SYSTEM_PROMPT.format(
            question=question,
            answer=answer,
        )

        try:
            raw_text = self._call_groq(prompt, json_mode=True)

            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                raw_text = raw_text.rsplit("```", 1)[0]
                raw_text = raw_text.strip()

            evaluation = json.loads(raw_text)
            return self._validate_evaluation(evaluation)

        except json.JSONDecodeError as e:
            print(f"[Evaluator] JSON parse error: {e}")
            print(f"[Evaluator] Raw response: {raw_text}")
            return self._error_evaluation("Failed to parse LLM evaluation response.")

        except Exception as e:
            print(f"[Evaluator] Error: {e}")
            return self._error_evaluation(str(e))

    def generate_weakness_followup(
        self, question: str, answer: str, weaknesses: list
    ) -> str:
        """
        Generate a sharp follow-up question targeting the candidate's
        weakest areas identified during evaluation.
        """
        if not weaknesses:
            return None

        weaknesses_text = "\n".join(f"- {w}" for w in weaknesses)

        prompt = WEAKNESS_FOLLOWUP_PROMPT.format(
            weaknesses=weaknesses_text,
            question=question,
            answer=answer,
        )

        try:
            raw_text = self._call_groq(prompt, json_mode=False)
        except Exception as e:
            print(f"[Evaluator] Follow-up generation error: {e}")
            return None

    # ════════════════════════════════════════════════════════════
    #  Validation Helpers
    # ════════════════════════════════════════════════════════════

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

        # Recalculate overall as simple average (preserved for compat)
        scores = [data[f] for f in score_fields]
        data["overall_score"] = round(sum(scores) / len(scores), 2)

        # Compute weighted overall score
        data["weighted_overall_score"] = compute_weighted_score(data)

        # Compute weakest dimension
        min_score = min(scores)
        min_idx = scores.index(min_score)
        data["weakest_dimension"] = score_fields[min_idx]

        # Validate hire_signal
        valid_signals = ["Strong Hire", "Hire", "Borderline", "No Hire"]
        if data.get("hire_signal") not in valid_signals:
            data["hire_signal"] = self._derive_hire_signal(data["weighted_overall_score"])

        # Validate STAR breakdown
        star = data.get("star_breakdown", {})
        data["star_breakdown"] = {
            "situation_present": bool(star.get("situation_present", False)),
            "task_present": bool(star.get("task_present", False)),
            "action_present": bool(star.get("action_present", False)),
            "result_present": bool(star.get("result_present", False)),
        }

        return data

    def _validate_decision(self, data: dict) -> dict:
        """Validate the decision block from adaptive response."""
        if data.get("type") not in ("PROBE", "ADVANCE"):
            data["type"] = "ADVANCE"
        if not data.get("next_question"):
            data["next_question"] = "Can you share one specific project where you ran into a tough technical problem?"
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

        # Recalculate overall as average
        scores = [data[f] for f in score_fields]
        data["overall_score"] = round(sum(scores) / len(scores), 2)

        # Add canonical short names alongside legacy _score names
        data["clarity"] = data["clarity_score"]
        data["structure"] = data["structure_score"]
        data["confidence"] = data["confidence_score"]
        data["ownership"] = data["ownership_score"]
        data["leadership"] = data["leadership_score"]
        data["result_orientation"] = data["result_score"]

        data["weighted_overall_score"] = compute_weighted_score(data)

        # Compute weakest dimension
        dimension_names = [
            "clarity", "structure", "confidence",
            "ownership", "leadership", "result_orientation",
        ]
        min_score = min(scores)
        min_idx = scores.index(min_score)
        data["weakest_dimension"] = dimension_names[min_idx]

        # Validate hire_signal
        valid_signals = ["Strong Hire", "Hire", "Borderline", "No Hire"]
        if data.get("hire_signal") not in valid_signals:
            data["hire_signal"] = self._derive_hire_signal(data["weighted_overall_score"])

        # Ensure lists
        data.setdefault("strengths", [])
        data.setdefault("weaknesses", [])

        return data

    def _derive_hire_signal(self, overall_score: float) -> str:
        """Derive hire signal from calibrated weighted score."""
        if overall_score >= 4.2:
            return "Strong Hire"
        elif overall_score >= 3.4:
            return "Hire"
        elif overall_score >= 2.5:
            return "Borderline"
        else:
            return "No Hire"

    def _empty_evaluation(self) -> dict:
        """Return a default evaluation for empty/trivial answers."""
        return {
            "clarity_score": 1, "clarity": 1,
            "structure_score": 1, "structure": 1,
            "confidence_score": 1, "confidence": 1,
            "ownership_score": 1, "ownership": 1,
            "leadership_score": 1, "leadership": 1,
            "result_score": 1, "result_orientation": 1,
            "strengths": [],
            "weaknesses": ["Answer too short or empty to evaluate."],
            "overall_score": 1.0,
            "weighted_overall_score": compute_weighted_score({
                "clarity": 1, "structure": 1, "confidence": 1,
                "ownership": 1, "leadership": 1, "result_orientation": 1,
            }),
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
                "next_question": "Let's make this concrete. Please explain one practical technical approach you would take, including the steps, tools, trade-offs, and how you would validate it.",
            },
        }
