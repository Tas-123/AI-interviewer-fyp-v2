"""
Decision Engine — Determines the next interview action based on
the current context and the candidate's latest answer.

Uses adaptive evaluation (PROBE/ADVANCE) for intelligent follow-up decisions.
"""

from dialogue.states import InterviewState
from dialogue.followup_policy import classify_followup_type


# Threshold: if overall evaluation score is at or below this,
# trigger a weakness-based follow-up instead of advancing.
WEAKNESS_FOLLOWUP_THRESHOLD = 2.5


class DecisionEngine:

    def _attach_followup_metadata(
        self, result: dict, adaptive_result: dict, context
    ) -> dict:
        evaluation = adaptive_result.get("evaluation", {})
        decision = adaptive_result.get("decision", {})
        answer_text = getattr(context, "latest_answer_for_decision", "")
        followup_type, followup_reason = classify_followup_type(
            evaluation,
            decision,
            domain=result.get("domain", ""),
            answer_word_count=len(str(answer_text).split()),
            engine_reason=result.get("reason", ""),
        )
        result["followup_type"] = followup_type
        result["followup_reason"] = followup_reason
        return result

    def decide(self, context, latest_answer):
        """
        Decide next question/topic based on current context and latest answer.
        Returns an action dict consumed by LLMAdapter.generate().
        """

        # ── INTRO → greet the candidate ─────────────────────────
        if context.state == InterviewState.INTRO:
            context.state = InterviewState.TECHNICAL
            return {"type": "intro"}

        # ── Check if latest evaluation warrants a weakness follow-up ──
        latest_eval = context.get_latest_evaluation()
        if latest_eval and self._should_followup_on_weakness(latest_eval, context):
            active_domain = self._get_active_domain(context)

            # Allow only limited probing per domain.
            if hasattr(context, "can_probe_domain") and context.can_probe_domain(active_domain):
                context.mark_domain_probe(active_domain)
                return {
                    "type": "followup",
                    "topic": self._domain_to_topic(active_domain),
                    "domain": active_domain,
                    "weaknesses": latest_eval.get("weaknesses", []),
                    "reason": "weakness_probe_allowed",
                }

            # Probe limit reached: mark this domain covered and move forward.
            if hasattr(context, "mark_domain_covered"):
                context.mark_domain_covered(active_domain)

            next_domain = self._advance_to_next_domain(context)
            if next_domain is None:
                context.state = InterviewState.WRAPUP
                return {"type": "closing"}

            return {
                "type": "ask",
                "topic": self._domain_to_topic(next_domain),
                "domain": next_domain,
                "difficulty": "medium",
                "reason": "probe_limit_reached_moving_to_next_domain",
            }

        # ── TECHNICAL → ask questions on resume skills ──────────
        if context.state == InterviewState.TECHNICAL:
            return self._handle_technical(context, latest_answer)

        # ── BEHAVIORAL → ask HR behavioral questions ────────────
        if context.state == InterviewState.BEHAVIORAL:
            return self._handle_behavioral(context, latest_answer)

        # ── WRAPUP → close the interview ────────────────────────
        if context.state == InterviewState.WRAPUP:
            return {"type": "closing"}

        # ── Fallback — should never reach here ──────────────────
        return {"type": "closing"}

    # ════════════════════════════════════════════════════════════
    #  State Handlers
    # ════════════════════════════════════════════════════════════

    def _domain_to_topic(self, domain: str) -> str:
        """Map Junior AI Engineer blueprint domain to LLM topic label."""
        mapping = {
            "project_overview": "project overview",
            "python": "python",
            "machine_learning": "machine learning",
            "data_preprocessing": "data preprocessing",
            "model_evaluation": "model evaluation",
            "nlp_speech_ai": "nlp / speech ai",
            "apis_backend": "apis / backend",
            "deployment": "deployment",
            "debugging_problem_solving": "debugging / problem solving",
            "behavioral_ownership": "behavioral ownership",
        }
        return mapping.get(domain, domain or "general")

    def _get_active_domain(self, context):
        """Return current active blueprint domain."""
        domain = getattr(context, "current_domain", None)
        if not domain and hasattr(context, "get_next_domain"):
            domain = context.get_next_domain()
        return domain

    def _advance_to_next_domain(self, context):
        """Move to the next domain that still needs coverage."""
        if not hasattr(context, "get_next_domain"):
            return None
        next_domain = context.get_next_domain()
        if next_domain:
            context.current_domain = next_domain
        return next_domain

    def _handle_technical(self, context, latest_answer):
        """Handle TECHNICAL state using Junior AI Engineer blueprint."""
        if getattr(context, "turn_count", 0) >= getattr(context, "max_total_interview_turns", 12):
            context.state = InterviewState.WRAPUP
            return {"type": "closing"}

        domain = context.get_next_domain() if hasattr(context, "get_next_domain") else None

        if domain is None:
            context.state = InterviewState.BEHAVIORAL
            category = context.get_next_behavioral_category()
            return {
                "type": "ask",
                "topic": "behavioral",
                "domain": "behavioral_ownership",
                "category": category,
                "difficulty": "medium",
            }

        context.current_domain = domain

        if hasattr(context, "mark_domain_covered"):
            context.mark_domain_covered(domain)

        return {
            "type": "ask",
            "topic": self._domain_to_topic(domain),
            "domain": domain,
            "difficulty": "medium",
        }

    def _handle_behavioral(self, context, latest_answer):
        """Handle the BEHAVIORAL interview state."""
        context.topic_coverage["behavioral"] += 1

        # Allow up to 5 behavioral turns, then wrap up
        if context.topic_coverage["behavioral"] >= 5:
            context.state = InterviewState.WRAPUP
            return {"type": "closing"}

        category = context.get_next_behavioral_category()
        return {
            "type": "ask",
            "topic": "behavioral",
            "category": category,
            "difficulty": "medium",
        }

    # ════════════════════════════════════════════════════════════
    #  Adaptive Decision (PROBE / ADVANCE)
    # ════════════════════════════════════════════════════════════

    def decide_from_adaptive(self, adaptive_result: dict, context) -> dict:
        """Consume adaptive evaluation and enforce interview policy with follow-up metadata."""
        result = self._decide_from_adaptive_impl(adaptive_result, context)
        return self._attach_followup_metadata(result, adaptive_result, context)

    def _decide_from_adaptive_impl(self, adaptive_result: dict, context) -> dict:
        """
        Consume Evaluator.adaptive_evaluate() result and enforce interview policy.

        Key rule:
        - PROBE is allowed only up to max_probes_per_domain.
        - After probe limit, force movement to the next Junior AI Engineer domain.
        """
        decision = adaptive_result.get("decision", {})
        decision_type = decision.get("type", "ADVANCE")

        if getattr(context, "turn_count", 0) >= getattr(context, "max_total_interview_turns", 12):
            context.state = InterviewState.WRAPUP
            return {
                "action": "closing",
                "type": "closing",
                "next_question": "Thank you for your time. This concludes the interview.",
                "decision_type": "CLOSING",
            }

        active_domain = self._get_active_domain(context)

        if decision_type == "PROBE":
            evaluation = adaptive_result.get("evaluation", {})
            answer_text = getattr(context, "latest_answer_for_decision", "")
            weighted_score = evaluation.get("weighted_overall_score", evaluation.get("overall_score", 0))
            weakest = evaluation.get("weakest_dimension", "")
            answer_word_count = len(str(answer_text).split())

            # Strict probing policy:
            # For Junior AI Engineer interviews, coverage beats endless probing.
            # Technical domains should usually advance unless the answer is extremely weak.
            if active_domain == "project_overview":
                critical_probe = (
                    weighted_score <= 2.3
                    or answer_word_count < 18
                    or weakest in ["ownership", "result_orientation"]
                )
            elif active_domain == "behavioral_ownership":
                critical_probe = (
                    weighted_score <= 2.3
                    or answer_word_count < 18
                    or weakest in ["ownership", "leadership", "result_orientation"]
                )
            else:
                # Controlled adaptive follow-up policy for technical domains:
                # We DO want context-based follow-ups because this is a core project feature.
                # But we still keep max_probes_per_domain = 1 to prevent endless interviews.
                technical_domains = [
                    "python",
                    "machine_learning",
                    "data_preprocessing",
                    "model_evaluation",
                    "nlp_speech_ai",
                    "apis_backend",
                    "deployment",
                    "debugging_problem_solving",
                ]

                # A decent/specific answer deserves one answer-aware technical follow-up.
                # Very short answers also get one repair follow-up.
                if active_domain in technical_domains:
                    critical_probe = (
                        answer_word_count >= 18
                        and weighted_score >= 2.5
                    ) or (
                        weighted_score <= 2.0
                        or answer_word_count < 8
                    )
                else:
                    critical_probe = (
                        weighted_score <= 2.0
                        or answer_word_count < 8
                    )

            if critical_probe and hasattr(context, "can_probe_domain") and context.can_probe_domain(active_domain):
                context.mark_domain_probe(active_domain)
                return {
                    "action": "probe",
                    "type": "followup",
                    "topic": self._domain_to_topic(active_domain),
                    "domain": active_domain,
                    "next_question": decision.get("next_question", ""),
                    "decision_type": "PROBE",
                    "reason": "critical_probe_allowed",
                }

            # Probe limit reached: do not use evaluator's follow-up.
            if hasattr(context, "mark_domain_covered"):
                context.mark_domain_covered(active_domain)

            next_domain = self._advance_to_next_domain(context)
            if next_domain is None:
                context.state = InterviewState.WRAPUP
                return {
                    "action": "closing",
                    "type": "closing",
                    "next_question": "Thank you for your time. This concludes the interview.",
                    "decision_type": "CLOSING",
                    "reason": "all_domains_complete",
                }

            return {
                "action": "advance",
                "type": "ask",
                "topic": self._domain_to_topic(next_domain),
                "domain": next_domain,
                "next_question": "",
                "decision_type": "ADVANCE",
                "reason": "probe_limit_reached_moving_to_next_domain",
            }

        # ADVANCE can still produce a controlled answer-aware follow-up.
        # This preserves the project's adaptive/contextual questioning feature
        # without making every domain too long.
        evaluation = adaptive_result.get("evaluation", {})
        answer_text = getattr(context, "latest_answer_for_decision", "")
        weighted_score = evaluation.get("weighted_overall_score", evaluation.get("overall_score", 0))
        answer_word_count = len(str(answer_text).split())

        high_value_context_domains = [
            "project_overview",
            "python",
            "machine_learning",
            "apis_backend",
            "deployment",
        ]

        should_context_followup = (
            active_domain in high_value_context_domains
            and weighted_score >= 2.8
            and answer_word_count >= 18
            and hasattr(context, "can_context_followup")
            and context.can_context_followup(active_domain)
        )

        if should_context_followup:
            context.mark_context_followup(active_domain)

            # Count context follow-up as the domain's one allowed probe too.
            # This prevents an extra repair/behavioral probe immediately after
            # a context follow-up answer.
            if hasattr(context, "mark_domain_probe"):
                context.mark_domain_probe(active_domain)

            return {
                "action": "probe",
                "type": "followup",
                "topic": self._domain_to_topic(active_domain),
                "domain": active_domain,
                "next_question": decision.get("next_question", ""),
                "decision_type": "PROBE",
                "reason": "context_followup_after_good_answer",
            }

        # ADVANCE: mark current domain covered and move to next domain.
        if hasattr(context, "mark_domain_covered"):
            context.mark_domain_covered(active_domain)

        next_domain = self._advance_to_next_domain(context)
        if next_domain is None:
            context.state = InterviewState.WRAPUP
            return {
                "action": "closing",
                "type": "closing",
                "next_question": "Thank you for your time. This concludes the interview.",
                "decision_type": "CLOSING",
            }

        return {
            "action": "advance",
            "type": "ask",
            "topic": self._domain_to_topic(next_domain),
            "domain": next_domain,
            "next_question": decision.get("next_question", ""),
            "decision_type": "ADVANCE",
        }

    def _should_followup_on_weakness(self, evaluation, context):
        """
        Determine whether to trigger a weakness-based follow-up.
        Conditions:
        - Overall score is at or below the threshold
        - There are weaknesses identified
        - We haven't already done a weakness follow-up for this turn
          (prevent infinite loops — max 1 weakness follow-up per answer)
        """
        overall = evaluation.get("overall_score", 5.0)
        weaknesses = evaluation.get("weaknesses", [])
        last_was_followup = (
            len(context.question_history) > 0
            and context.question_history[-1].startswith("[Weakness Follow-up]")
        )

        return (
            overall <= WEAKNESS_FOLLOWUP_THRESHOLD
            and len(weaknesses) > 0
            and not last_was_followup
        )

    def _evaluate_answer(self, answer: str):
        """
        Simple heuristic evaluation based on word count.
        Used for technical answer quality (the LLM Evaluator handles
        detailed behavioral scoring separately).
        """
        word_count = len(answer.split())
        if word_count < 5:
            return "very_weak"
        elif word_count < 15:
            return "weak"
        elif word_count < 40:
            return "average"
        else:
            return "strong"

    def _get_next_technical_topic(self, context):
        """Return next technical skill with coverage < 2, or None."""
        for skill in context.skills:
            if context.topic_coverage.get(skill, 0) < 2:
                return skill
        return None