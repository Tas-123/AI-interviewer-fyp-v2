"""
Dialogue Manager -- Orchestrates one turn of the interview.
Coordinates between DecisionEngine, LLMAdapter, Evaluator, InterviewContext,
and Database persistence layer.

Supports two evaluation paths:
  1. ADAPTIVE (default) -- Evaluator scores + decides next question in one LLM call
  2. LEGACY (fallback)  -- Separate evaluate() + decide() + generate() pipeline
"""

from dialogue.context import InterviewContext
from dialogue.guards.pipeline import GuardPipeline
from dialogue.guards.types import GuardContext, GuardResult
from dialogue.followup_policy import build_followup_label
from dialogue.transcript_utils import clean_live_transcript
from dialogue.decision_engine import DecisionEngine
from dialogue.llm_adapter import LLMAdapter
from dialogue.evaluator import Evaluator


class DialogueManager:

    def __init__(self, resume_data, session_id=None):
        self.session_id = session_id
        self.context = InterviewContext(resume_data)
        self.engine = DecisionEngine()
        self.llm = LLMAdapter()
        self.evaluator = Evaluator()
        self.latency_history = []  # List of latency_ms per turn
        self.guard_pipeline = GuardPipeline(
            llm_client=self.llm.client,
            llm_model=self.llm.model,
        )

    def _debug_live_log(self, label: str, value):
        """
        Write clean human-readable interview flow logs.
        This helps separate bot questions, candidate transcripts, decisions, and evaluations.
        """
        try:
            from core.config import settings
            import datetime
            import json

            if not settings.debug_live_logging:
                return

            log_file = settings.live_debug_log
            log_file.parent.mkdir(parents=True, exist_ok=True)

            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                value_text = str(value)

            with log_file.open("a", encoding="utf-8") as f:
                f.write(f"\n[{ts}] {label}\n")
                f.write(value_text.strip() + "\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            print(f"[LiveDebugLog] Failed: {e}")


    def _clean_live_transcript(self, text: str) -> str:
        """Backward-compatible shim — delegates to shared transcript utils."""
        return clean_live_transcript(text)

    def _record_non_evaluated_event(self, event_type: str, transcript: str, **extra):
        if not hasattr(self.context, "non_evaluated_events"):
            self.context.non_evaluated_events = []
        payload = {"type": event_type, "transcript": transcript, **extra}
        self.context.non_evaluated_events.append(payload)

    def _response_from_guard(
        self, guard_hit: GuardResult, transcript: str, last_question: str
    ) -> dict:
        self._record_non_evaluated_event(
            guard_hit.decision_type,
            transcript,
            response=guard_hit.response_text,
            question=last_question,
            metadata=guard_hit.metadata,
        )
        return {
            "question": guard_hit.response_text or "",
            "evaluation": None,
            "decision_type": guard_hit.decision_type,
            "latency_ms": 0,
        }

    def handle_turn(self, transcript):
        raw_transcript_for_debug = transcript
        transcript = self._clean_live_transcript(transcript)

        try:
            last_q_for_debug = self.context.question_history[-1] if getattr(self.context, "question_history", []) else ""
            self._debug_live_log("BOT_LAST_QUESTION", last_q_for_debug)
            self._debug_live_log("CANDIDATE_RAW_TRANSCRIPT", raw_transcript_for_debug)
            self._debug_live_log("CANDIDATE_CLEAN_TRANSCRIPT", transcript)
        except Exception:
            pass

        def final_log_and_return(res, decision_val):
            try:
                self._debug_live_log("DECISION", decision_val)
                self._debug_live_log("BOT_NEXT_QUESTION", res.get("question", ""))
            except Exception:
                pass
            return res

        """
        Handle one conversation turn:
        1. If INTRO state -> generate greeting (no evaluation)
        2. Otherwise -> use adaptive evaluation (score + decide + generate in one call)
        3. Fallback to legacy pipeline if adaptive fails
        """

        # -- INTRO: no answer to evaluate yet --
        if not transcript and self.context.state.value == "intro":
            action = self.engine.decide(self.context, transcript)
            question = self.llm.generate(action, self.context)
            self.context.add_turn(question, transcript)
            res = {
                "question": question, "evaluation": None,
                "decision_type": None, "latency_ms": 0,
            }
            return final_log_and_return(res, "INTRO")

        # -- WRAPUP: close the interview --
        if self.context.state.value == "wrapup":
            question = "Thank you for your time. This concludes the interview."
            self.context.add_turn(question, transcript)
            res = {
                "question": question, "evaluation": None,
                "decision_type": "CLOSING", "latency_ms": 0,
            }
            return final_log_and_return(res, "CLOSING")

        # -- ADAPTIVE PATH: evaluate + decide in one call --
        last_question = (
            self.context.question_history[-1]
            if self.context.question_history
            else ""
        )

        # -- Pre-evaluation guard pipeline --
        guard_ctx = GuardContext(
            transcript=transcript,
            last_question=last_question,
            interview_context=self.context,
            llm_client=self.llm.client,
            llm_model=self.llm.model,
        )
        guard_hit = self.guard_pipeline.run(guard_ctx)
        if guard_hit:
            return final_log_and_return(
                self._response_from_guard(guard_hit, transcript, last_question),
                f"{guard_hit.decision_type} - ignored transcript, no scoring",
            )

        try:
            adaptive_result = self.evaluator.adaptive_evaluate(
                question=last_question,
                answer=transcript,
                previous_evaluations=self.context.get_previous_evaluations_summary(),
                interview_stage=self.context.interview_stage,
            )

            evaluation = adaptive_result.get("evaluation", {})
            decision = adaptive_result.get("decision", {})
            latency_ms = adaptive_result.get("latency_ms", 0)
            self.latency_history.append(latency_ms)

            # Store evaluation in context
            self.context.add_evaluation(evaluation)

            # Capture the domain of the question that was just answered BEFORE
            # DecisionEngine advances current_domain to the next domain.
            answered_domain = getattr(self.context, "current_domain", "")

            # Let the engine handle state transitions.
            # Store the current transcript temporarily so DecisionEngine can make
            # probe decisions using the actual current answer, not the previous turn.
            self.context.latest_answer_for_decision = transcript

            engine_result = self.engine.decide_from_adaptive(
                adaptive_result, self.context
            )

            # Decide final next question using DecisionEngine policy.
            # If the engine allows the PROBE, use evaluator's follow-up.
            # If probe limit is reached, ignore evaluator follow-up and generate next domain question.
            engine_decision_type = engine_result.get("decision_type", decision.get("type", "ADVANCE"))
            engine_action_type = engine_result.get("type", "")
            engine_reason = engine_result.get("reason", "")

            if engine_reason == "probe_limit_reached_moving_to_next_domain" or engine_action_type == "ask":
                # Force next blueprint domain question through LLMAdapter.
                question = self.llm.generate(engine_result, self.context)
                decision_type = "ADVANCE"
            elif engine_action_type == "closing" or engine_decision_type == "CLOSING":
                question = engine_result.get("next_question", "Thank you for your time. This concludes the interview.")
                decision_type = "CLOSING"
            else:
                question = decision.get("next_question", "")
                decision_type = decision.get("type", "ADVANCE")

            # Record this turn
            if decision_type == "PROBE":
                question = f"[Follow-up] {question}"

            decision_log = {
                "decision_type": decision_type,
                "engine_decision_type": engine_decision_type,
                "engine_action_type": engine_action_type,
                "engine_reason": engine_reason,
                "weakest_dimension": evaluation.get("weakest_dimension", ""),
                "weighted_score": evaluation.get("weighted_overall_score", evaluation.get("overall_score", 0)),
                "hire_signal": evaluation.get("hire_signal", ""),
            }

            # Record this turn (skip error strings from question history)
            if question.startswith("[Error"):
                self.context.transcript_history.append(transcript)
                self.context.turn_count += 1
            else:
                self.context.add_turn(question, transcript)

            # Store adaptive/contextual questioning trace for final report.
            # This proves why the system asked a follow-up or moved forward.
            try:
                weakest_dimension = evaluation.get("weakest_dimension", "unknown")
                decision_type = engine_result.get("decision_type") or decision.get("type", "UNKNOWN")
                next_question = (
                    question.replace("[Follow-up]", "")
                    .replace("[follow-up]", "")
                    .replace("Follow-up:", "")
                    .replace("follow-up:", "")
                    .strip()
                )

                follow_up_reason = self._build_follow_up_reason(
                    weakest_dimension=weakest_dimension,
                    decision_type=decision_type,
                    evaluation=evaluation,
                    answer=transcript,
                )
                followup_type = engine_result.get("followup_type", "")
                policy_followup_reason = engine_result.get("followup_reason", "")
                if policy_followup_reason:
                    follow_up_reason = policy_followup_reason

                skill_focus = self._infer_skill_focus(last_question, transcript)

                clean_last_question = (
                    last_question.replace("[Follow-up]", "")
                    .replace("[follow-up]", "")
                    .replace("Follow-up:", "")
                    .replace("follow-up:", "")
                    .strip()
                )

                self.context.add_adaptive_trace({
                    "turn": self.context.turn_count,
                    "question_answered": clean_last_question,
                    "candidate_answer": transcript,
                    "decision_type": decision_type,
                    "engine_action": engine_result.get("type", ""),
                    "engine_reason": engine_result.get("reason", ""),
                    "domain": answered_domain,
                    "next_domain": engine_result.get("domain", getattr(self.context, "current_domain", "")),
                    "weakest_dimension": weakest_dimension,
                    "follow_up_reason": follow_up_reason,
                    "followup_type": followup_type,
                    "followup_label": build_followup_label(followup_type) if followup_type else "",
                    "guard_passed": True,
                    "next_question": next_question,
                    "skill_focus": skill_focus,
                    "interview_stage": self.context.interview_stage,
                    "scores": {
                        "clarity": evaluation.get("clarity", 0),
                        "structure": evaluation.get("structure", 0),
                        "confidence": evaluation.get("confidence", 0),
                        "ownership": evaluation.get("ownership", 0),
                        "leadership": evaluation.get("leadership", 0),
                        "result_orientation": evaluation.get("result_orientation", 0),
                        "overall_score": evaluation.get("overall_score", 0),
                        "weighted_overall_score": evaluation.get("weighted_overall_score", 0),
                    },
                    "star_breakdown": evaluation.get("star_breakdown", {}),
                    "hire_signal": evaluation.get("hire_signal", "N/A"),
                })
            except Exception as trace_error:
                print(f"[Adaptive Trace Warning] Could not store trace: {trace_error}")

            # Persist to DB (non-blocking, graceful fallback)
            self._save_response_to_db(
                question=question,
                answer=transcript,
                evaluation=evaluation,
                decision_type=decision_type,
                latency_ms=latency_ms,
            )

            res = {
                "question": question,
                "evaluation": evaluation,
                "decision_type": decision_type,
                "latency_ms": latency_ms,
            }
            return final_log_and_return(res, decision_log)

        except Exception as e:
            print(f"[DialogueManager] Adaptive path failed, using legacy: {e}")
            res = self._legacy_handle_turn(transcript)
            return final_log_and_return(res, "LEGACY")

    def _legacy_handle_turn(self, transcript):
        """
        Legacy fallback pipeline: separate evaluate -> decide -> generate.
        """
        evaluation = None
        if transcript and self.context.question_history:
            last_question = self.context.question_history[-1]
            evaluation = self.evaluator.evaluate(last_question, transcript)
            self.context.add_evaluation(evaluation)

        action = self.engine.decide(self.context, transcript)

        if action.get("type") == "weakness_followup":
            last_question = (
                self.context.question_history[-1]
                if self.context.question_history
                else ""
            )
            weaknesses = action.get("weaknesses", [])
            followup = self.evaluator.generate_weakness_followup(
                question=last_question,
                answer=transcript,
                weaknesses=weaknesses,
            )
            question = (
                f"[Weakness Follow-up] {followup}"
                if followup
                else self.llm.generate(action, self.context)
            )
        else:
            question = self.llm.generate(action, self.context)

        self.context.add_turn(question, transcript)

        return {
            "question": question,
            "evaluation": evaluation,
            "decision_type": "LEGACY",
            "latency_ms": 0,
        }



    # -- Backward-compatible guard shims (root regression tests) --
    def _looks_like_bot_question_echo(self, transcript: str, last_question: str = "") -> bool:
        from dialogue.guards.echo_guard import looks_like_bot_question_echo
        return looks_like_bot_question_echo(transcript, last_question)

    def _short_repeat_question(self, last_question: str = "") -> str:
        from dialogue.guards.echo_guard import short_repeat_question
        return short_repeat_question(last_question)

    def _classify_candidate_intent(self, transcript: str, last_question: str = "") -> str:
        from dialogue.guards.intent_guard import classify_candidate_intent
        return classify_candidate_intent(
            transcript, last_question,
            llm_client=self.llm.client, llm_model=self.llm.model,
        )

    def _should_use_semantic_intent_classifier(self, transcript: str) -> bool:
        from dialogue.guards.intent_guard import should_use_semantic_intent_classifier
        return should_use_semantic_intent_classifier(transcript)

    def _semantic_intent_classify(self, transcript: str, last_question: str = "") -> str:
        from dialogue.guards.intent_guard import semantic_intent_classify
        return semantic_intent_classify(
            transcript, last_question,
            llm_client=self.llm.client, llm_model=self.llm.model,
        )

    def _looks_like_incomplete_transcript(self, transcript: str, last_question: str = "") -> bool:
        from dialogue.guards.incomplete_guard import looks_like_incomplete_transcript
        return looks_like_incomplete_transcript(transcript, last_question)

    def _incomplete_transcript_response(self, transcript: str, last_question: str = "") -> str:
        from dialogue.guards.incomplete_guard import incomplete_transcript_response
        return incomplete_transcript_response(transcript, last_question)

    def _is_answer_relevant_to_question(self, transcript: str, last_question: str) -> bool:
        from dialogue.guards.domain_guard import is_answer_relevant_to_question
        return is_answer_relevant_to_question(transcript, last_question)

    def _domain_relevance_redirect_response(self, last_question: str) -> str:
        from dialogue.guards.domain_guard import domain_relevance_redirect_response
        return domain_relevance_redirect_response(last_question)

    def _intent_redirect_response(self, intent: str, transcript: str, last_question: str = "") -> str:
        from dialogue.guards.intent_guard import intent_redirect_response
        return intent_redirect_response(intent, transcript, last_question)

    def _build_follow_up_reason(self, weakest_dimension, decision_type, evaluation, answer):
        """Create a readable reason explaining why the next question was selected."""
        if not answer or len(answer.strip()) < 10:
            return "Candidate answer was too short, so the system needed clarification."

        reason_map = {
            "clarity": "Candidate response lacked clarity, so the system asked for a clearer explanation.",
            "structure": "Candidate response was not well structured, so the system asked for a more organized explanation.",
            "confidence": "Candidate response showed limited confidence, so the system asked for more specific evidence.",
            "ownership": "Candidate did not clearly explain personal contribution, so the system asked about ownership.",
            "leadership": "Candidate did not show leadership or collaboration evidence, so the system asked a leadership-oriented follow-up.",
            "result_orientation": "Candidate did not provide measurable impact or results, so the system asked about outcomes.",
        }

        star = evaluation.get("star_breakdown", {}) if isinstance(evaluation, dict) else {}

        technical_domains = {
            "python",
            "machine_learning",
            "data_preprocessing",
            "model_evaluation",
            "nlp_speech_ai",
            "apis_backend",
            "deployment",
            "debugging_problem_solving",
            "technical",
        }
        current_domain = str(getattr(self.context, "current_domain", "") or "").lower()

        if star and not star.get("result_present", True):
            if current_domain in technical_domains:
                return "Candidate answer needed more concrete technical detail, so the system asked for exact steps, reasoning, and validation."
            return "Candidate answer needed more concrete evidence or explanation, so the system asked for clearer steps, reasoning, or validation."

        if str(decision_type).upper() == "PROBE":
            return reason_map.get(
                weakest_dimension,
                "Candidate answer needed deeper detail, so the system asked a contextual follow-up."
            )

        return "Candidate answer was sufficient for this stage, so the system moved toward the next interview point."

    def _infer_skill_focus(self, question, answer):
        """Infer which resume/role skill this turn most likely assessed."""
        combined = f"{question} {answer}".lower()

        for skill in getattr(self.context, "skills", []):
            if skill and skill.lower() in combined:
                return skill

        fallback_keywords = {
            "python": ["python", "django", "fastapi", "script"],
            "machine learning": ["machine learning", "ml", "model", "training", "dataset"],
            "deep learning": ["deep learning", "neural", "cnn", "ann", "pytorch", "tensorflow"],
            "nlp / speech ai": ["speech", "stt", "tts", "whisper", "deepgram", "cartesia", "audio"],
            "backend / api": ["api", "backend", "websocket", "server", "database"],
            "deployment": ["deploy", "deployment", "hosting", "server", "production"],
        }

        for skill, keywords in fallback_keywords.items():
            if any(k in combined for k in keywords):
                return skill

        if getattr(self.context, "state", None):
            return self.context.state.value

        return "general"

    def _save_response_to_db(self, question, answer, evaluation, decision_type, latency_ms):
        """Persist a turn response to Postgres (graceful, non-blocking)."""
        if not self.session_id:
            return
        try:
            from dialogue.database import save_response
            save_response(
                session_id=self.session_id,
                turn_number=self.context.turn_count,
                question_text=question,
                answer_text=answer,
                weighted_score=evaluation.get("weighted_overall_score", 0),
                raw_score=evaluation.get("overall_score", 0),
                star_breakdown=evaluation.get("star_breakdown", {}),
                stage=self.context.interview_stage,
                latency_ms=latency_ms,
                decision_type=decision_type,
                weakest_dimension=evaluation.get("weakest_dimension", ""),
            )
        except Exception as e:
            print(f"[DialogueManager] DB save_response failed (non-critical): {e}")

    def get_status(self):
        """Return current interview status for debugging / API responses."""
        from dialogue.analytics import (
            detect_performance_trend,
            compute_consistency_rating,
        )

        status = {
            "state": self.context.state.value,
            "interview_stage": self.context.interview_stage,
            "turn_count": self.context.turn_count,
            "topic_coverage": dict(self.context.topic_coverage),
            "behavioral_categories_used": self.context.behavioral_categories_used,
            "evaluation_summary": self.context.get_evaluation_summary(),
        }

        # Live analytics (only if we have scored data)
        if self.context.weighted_score_history:
            trend = detect_performance_trend(
                self.context.weighted_score_history
            )
            consistency = compute_consistency_rating(
                self.context.weighted_score_history
            )
            status["performance_trend"] = trend["performance_trend_label"]
            status["consistency_rating"] = consistency["consistency_rating"]

        return status

    def get_final_report(self):
        """Generate the complete final interview report with all analytics."""
        from dialogue.analytics import (
            generate_final_report,
            sanitize_recruiter_summary_for_technical_interview,
        )
        report = generate_final_report(self.context)
        report = sanitize_recruiter_summary_for_technical_interview(report)

        # Final hard safety for Junior AI Engineer technical interview reports:
        # Never expose STAR-style report sections or STAR-heavy wording as the main evaluation basis.
        if isinstance(report, dict):
            report.pop("star_effectiveness_analysis", None)

            if "technical_evidence_analysis" not in report:
                report["technical_evidence_analysis"] = {
                    "framework": "Evidence-Based Junior AI Engineer Technical Competency Rubric",
                    "expected_level": "Beginner-to-intermediate practical understanding, not expert-level production mastery.",
                    "focus_areas": [
                        "technical_correctness",
                        "implementation_thinking",
                        "tool_and_framework_understanding",
                        "validation_and_testing",
                        "debugging_approach",
                        "communication_clarity",
                        "ownership_evidence",
                    ],
                    "note": (
                        "The candidate is evaluated on junior-level technical understanding, practical implementation, "
                        "validation/testing, debugging approach, clarity, and personal contribution."
                    ),
                }

            summary = report.get("recruiter_summary", {}) or {}
            bad_phrases = [
                "Candidate repeatedly missed result/impact in STAR-style answers.",
                "Ask for measurable project impact, outcomes, or success metrics.",
            ]

            for key in ["main_concerns", "recommended_follow_up_areas"]:
                if isinstance(summary.get(key), list):
                    summary[key] = [
                        item for item in summary[key]
                        if item not in bad_phrases
                        and "STAR" not in str(item)
                        and "result/impact" not in str(item)
                    ]

            report["recruiter_summary"] = summary

            for item in report.get("adaptive_questioning_trace", []) or []:
                reason = str(item.get("follow_up_reason", ""))
                if "result/impact" in reason or "STAR" in reason:
                    item["follow_up_reason"] = (
                        "Candidate answer needed more concrete technical detail, so the system asked for clearer steps, reasoning, or validation."
                    )
                item.pop("star_breakdown", None)

            # --- Report-time transcript cleanup ---
            # Reuse the existing STT dedup logic to clean repeated fragments
            # in candidate_answer and evidence_snippets before saving.
            for item in report.get("adaptive_questioning_trace", []) or []:
                raw = item.get("candidate_answer", "")
                if raw:
                    item["candidate_answer"] = self._clean_live_transcript(raw)

            scm = report.get("skill_coverage_map", {}) or {}
            for skill_data in scm.values():
                snippets = skill_data.get("evidence_snippets", [])
                if snippets:
                    skill_data["evidence_snippets"] = [
                        self._clean_live_transcript(s) for s in snippets
                    ]

        # Persist final scores to DB
        self._persist_session_finals(report)

        # Add latency metrics
        if self.latency_history:
            sorted_l = sorted(self.latency_history)
            n = len(sorted_l)
            report["latency_metrics"] = {
                "avg_ms": round(sum(sorted_l) / n, 2),
                "p95_ms": round(sorted_l[min(int(n * 0.95), n - 1)], 2),
                "max_ms": round(max(sorted_l), 2),
                "total_calls": n,
                "source": "in_memory",
            }
        else:
            report["latency_metrics"] = {
                "avg_ms": 0, "p95_ms": 0, "max_ms": 0,
                "total_calls": 0, "source": "no_data",
            }

        # Try to enrich from DB
        if self.session_id:
            try:
                from dialogue.database import get_latency_metrics
                db_metrics = get_latency_metrics(self.session_id)
                if db_metrics.get("source") == "postgres":
                    report["latency_metrics"] = db_metrics
            except Exception:
                pass

        return report

    def _persist_session_finals(self, report):
        """Persist final analytics to DB session record (graceful fallback)."""
        if not self.session_id:
            return
        try:
            from dialogue.database import update_session_finals
            ws = report.get("weighted_score_summary", {})
            trend = report.get("performance_trend_analysis", {})
            consistency = report.get("consistency_rating", {})
            update_session_finals(
                session_id=self.session_id,
                final_weighted_score=ws.get("avg_weighted_overall", 0.0),
                hire_signal=ws.get("final_hire_signal", "N/A"),
                trend_label=trend.get("performance_trend_label", "stable"),
                consistency_rating=consistency.get("consistency_rating", "N/A"),
            )
        except Exception as e:
            print(f"[DialogueManager] update_session_finals failed (non-critical): {e}")