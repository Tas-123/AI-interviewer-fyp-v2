"""
Dialogue Manager -- Orchestrates one turn of the interview.
Coordinates between DecisionEngine, LLMAdapter, Evaluator, InterviewContext,
and Database persistence layer.

Supports two evaluation paths:
  1. ADAPTIVE (default) -- Evaluator scores + decides next question in one LLM call
  2. LEGACY (fallback)  -- Separate evaluate() + decide() + generate() pipeline
"""

from dialogue.context import InterviewContext
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

    def _debug_live_log(self, label: str, value):
        """
        Write clean human-readable interview flow logs.
        This helps separate bot questions, candidate transcripts, decisions, and evaluations.
        """
        try:
            from pathlib import Path
            import datetime
            import json

            log_dir = Path(r"C:\Users\LENOVO\Desktop\ai_dialogue_manager\logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "live_interview_debug.log"

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
        """Clean repeated ASR fragments before evaluation and reporting."""
        import re

        original = (text or "").strip()
        if not original:
            return ""

        cleaned = re.sub(r"\s+", " ", original).strip()

        def norm_token(x):
            t = x.lower().strip(".,!?;:")
            # Normalize common contractions so "I'd" matches "I", etc.
            for suffix in ("'d", "'s", "'ll", "'ve", "'re", "'m",
                           "\u2019d", "\u2019s", "\u2019ll", "\u2019ve", "\u2019re", "\u2019m"):
                if t.endswith(suffix):
                    t = t[:-len(suffix)]
                    break
            return t

        def remove_adjacent_repeated_ngrams(tokens, max_n=14):
            changed = True
            while changed:
                changed = False
                for n in range(min(max_n, len(tokens)//2), 0, -1):
                    i = 0
                    out = []
                    while i < len(tokens):
                        cur = tokens[i:i+n]
                        nxt = tokens[i+n:i+2*n]

                        if len(cur) == n and [norm_token(x) for x in cur] == [norm_token(x) for x in nxt]:
                            out.extend(cur)
                            i += 2*n
                            changed = True

                            while i+n <= len(tokens) and [norm_token(x) for x in tokens[i:i+n]] == [norm_token(x) for x in cur]:
                                i += n
                        else:
                            out.append(tokens[i])
                            i += 1
                    tokens = out
            return tokens

        tokens = remove_adjacent_repeated_ngrams(cleaned.split())
        cleaned = " ".join(tokens)

        phrase_pattern = re.compile(
            r"\b((?:\w+[,.]?\s+){2,12}\w+[,.]?)(?:\s+\1\b)+",
            flags=re.IGNORECASE
        )

        previous = None
        while previous != cleaned:
            previous = cleaned
            cleaned = phrase_pattern.sub(r"\1", cleaned).strip()

        cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return original

        if len(original.split()) >= 10 and len(cleaned.split()) < max(5, int(len(original.split()) * 0.40)):
            return original

        return cleaned


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

        # Candidate intent gate:
        # Before scoring, classify whether the user is answering, asking for repeat,
        # asking for clarification, reporting audio issue, going off-topic, or echoing
        # an external prompt. Only ANSWER_ATTEMPT should be evaluated.
        if self._looks_like_bot_question_echo(transcript, last_question):
            if not hasattr(self.context, "non_evaluated_events"):
                self.context.non_evaluated_events = []
            self.context.non_evaluated_events.append({
                "type": "BOT_OR_EXTERNAL_PROMPT_ECHO",
                "transcript": transcript,
                "last_question": last_question,
            })

            echo_response = (
                "I detected that the interviewer prompt may have been repeated instead of a candidate answer. "
                "Please answer in your own words. "
                + self._short_repeat_question(last_question)
            )

            res = {
                "question": echo_response,
                "evaluation": None,
                "decision_type": "BOT_OR_EXTERNAL_PROMPT_ECHO",
                "latency_ms": 0,
            }
            return final_log_and_return(res, "BOT_OR_EXTERNAL_PROMPT_ECHO - ignored transcript, no scoring")

        candidate_intent = self._classify_candidate_intent(transcript, last_question)

        if candidate_intent != "ANSWER_ATTEMPT":
            question = self._intent_redirect_response(candidate_intent, transcript, last_question)

            # Store separately as non-evaluated event.
            if not hasattr(self.context, "non_evaluated_events"):
                self.context.non_evaluated_events = []

            self.context.non_evaluated_events.append({
                "type": candidate_intent,
                "transcript": transcript,
                "response": question,
            })

            res = {
                "question": question,
                "evaluation": None,
                "decision_type": candidate_intent,
                "latency_ms": 0,
            }
            return final_log_and_return(res, f"{candidate_intent} - ignored transcript, no scoring")

        # Incomplete transcript gate:
        # If STT only captured a tiny fragment, do not score it.
        # Ask the candidate to continue/repeat the current answer.
        if self._looks_like_incomplete_transcript(transcript, last_question):
            question = self._incomplete_transcript_response(transcript, last_question)

            if not hasattr(self.context, "non_evaluated_events"):
                self.context.non_evaluated_events = []

            self.context.non_evaluated_events.append({
                "type": "INCOMPLETE_TRANSCRIPT_REDIRECT",
                "transcript": transcript,
                "response": question,
                "question": last_question,
            })

            res = {
                "question": question,
                "evaluation": None,
                "decision_type": "INCOMPLETE_TRANSCRIPT_REDIRECT",
                "latency_ms": 0,
            }
            return final_log_and_return(res, "INCOMPLETE_TRANSCRIPT_REDIRECT - ignored transcript, no scoring")

        # Domain relevance gate:
        # If the candidate gives an answer attempt but it clearly does not answer
        # the current domain/question, do not score it. Redirect to the same question.
        if not self._is_answer_relevant_to_question(transcript, last_question):
            question = self._domain_relevance_redirect_response(last_question)

            if not hasattr(self.context, "non_evaluated_events"):
                self.context.non_evaluated_events = []

            self.context.non_evaluated_events.append({
                "type": "DOMAIN_RELEVANCE_REDIRECT",
                "transcript": transcript,
                "response": question,
                "question": last_question,
            })

            res = {
                "question": question,
                "evaluation": None,
                "decision_type": "DOMAIN_RELEVANCE_REDIRECT",
                "latency_ms": 0,
            }
            return final_log_and_return(res, "DOMAIN_RELEVANCE_REDIRECT - ignored transcript, no scoring")

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



    def _looks_like_bot_question_echo(self, transcript: str, last_question: str = "") -> bool:
        """
        Strictly detect when STT captured the bot/interviewer prompt itself.
        Do NOT mark normal candidate answers as echo just because they share words with the question.
        """
        import re

        t = (transcript or "").lower().strip()
        q = (last_question or "").lower().strip()

        if not t:
            return False

        candidate_answer_markers = [
            "i would", "i'd", "i detect", "training loss", "validation loss",
            "overfitting", "regularization", "dropout", "early stopping",
            "fastapi", "docker", "prometheus", "i will", "i used", "i worked",
            "i handled", "i compare", "i usually", "my project", "we used",
            "we built", "we handled", "missing values", "one hot encoding",
            "standard scaling"
        ]

        question_like_markers = [
            "can you", "could you", "please", "tell me about",
            "how would you", "what steps would you", "walk me through",
            "let's talk about", "question is", "answer this question"
        ]

        is_question_like = ("?" in t) or any(m in t for m in question_like_markers)
        has_candidate_answer_marker = any(m in t for m in candidate_answer_markers)

        external_prompt_markers = [
            "answer this question",
            "please answer this question",
            "stay on the current interview question",
            "your last response did not clearly answer",
            "please answer this directly",
            "chatgpt",
            "copy this answer",
            "repeat after me",
            "use this answer",
            "say this answer"
        ]
        if any(p in t for p in external_prompt_markers):
            return True

        echo_phrases = [
            "good morning",
            "welcome to the interview",
            "welcome to today's interview",
            "ai engineer position",
            "introduce yourself",
            "start by introducing yourself",
            "please start by introducing yourself",
            "can you please take a minute to introduce yourself",
            "i'm excited to learn more about your background",
            "tell me about one ai or machine learning project",
            "tell me about a recent ai or machine learning project",
        ]

        phrase_hits = sum(1 for p in echo_phrases if p in t)
        if phrase_hits >= 2:
            return True

        overlap = 0.0
        if q:
            def words(x):
                return set(re.findall(r"[a-zA-Z]{4,}", x))

            tw = words(t)
            qw = words(q)

            if len(tw) >= 6 and len(qw) >= 6:
                overlap = len(tw & qw) / max(1, len(qw))

        if has_candidate_answer_marker:
            if overlap >= 0.85:
                return True
            return False

        if is_question_like and overlap >= 0.85:
            return True

        return False


    def _short_repeat_question(self, last_question: str = "") -> str:
        """
        Repeat only the core interview question without replaying long greeting text.
        """
        q = (last_question or "").strip()
        lq = q.lower()

        if not q:
            return "Please answer the current interview question in your own words."

        # Any intro/project-overview greeting should be shortened.
        intro_markers = [
            "good morning",
            "welcome to the interview",
            "welcome to today's interview",
            "ai engineer position",
            "introducing yourself",
            "introduce yourself",
            "start by introducing yourself",
            "please start by introducing yourself",
            "tell me about a project",
            "tell me about one project",
            "project you've worked on",
            "project you have worked on",
            "showcases your ai",
            "machine learning skills",
            "ai or machine learning",
            "background and experience",
        ]

        if any(m in lq for m in intro_markers):
            return "Please introduce yourself and tell me about one AI or machine learning project you worked on."

        # Remove follow-up labels.
        for prefix in ["[Follow-up]", "[follow-up]", "Follow-up:", "follow-up:"]:
            q = q.replace(prefix, "").strip()

        # If a long greeting somehow remains, cut to a cleaner question.
        if len(q.split()) > 28 and ("?" in q):
            parts = [p.strip() for p in q.split(".") if p.strip()]
            question_parts = [p for p in parts if "?" in p]
            if question_parts:
                q = question_parts[-1].strip()

        return q


    def _classify_candidate_intent(self, transcript: str, last_question: str = "") -> str:
        """
        Classify candidate utterance before evaluation.
        This prevents repeat requests, audio issues, off-topic chatter, and
        external interviewer prompts from being scored as answers.
        """
        text = (transcript or "").strip().lower()
        if not text:
            return "AUDIO_ISSUE"

        clean = text.strip(" .,!?'\"").lower()
        words = clean.split()

        # Very short speech is often a mic/check/clarification signal, not an answer.
        audio_issue_phrases = [
            "hello", "hello?", "can you hear me", "are you there",
            "can't hear you", "cant hear you", "i can't hear you", "i cant hear you",
            "i could not hear", "could not hear", "couldn't hear", "i didn't hear",
            "i didnt hear", "not audible", "voice is low", "your voice is low",
            "audio issue", "mic issue"
        ]

        repeat_phrases = [
            "repeat", "repeat the question", "can you repeat", "please repeat",
            "say that again", "say it again", "ask again", "question again",
            "come again", "pardon"
        ]

        clarification_phrases = [
            "what do you mean", "what does that mean", "i don't understand",
            "i dont understand", "i did not understand", "didn't understand",
            "didnt understand", "couldn't understand", "couldnt understand",
            "i couldn't understand", "i couldnt understand",
            "sorry i couldn't understand", "sorry i couldnt understand",
            "can you explain", "please explain", "clarify",
            "can you clarify", "about what", "which one", "which model",
            "what model", "specific model", "what specific model",
            "what specific model are you talking about"
        ]

        external_prompt_phrases = [
            "i don't want buzzwords", "i dont want buzzwords",
            "don't want buzzwords", "dont want buzzwords",
            "skip the general stuff", "don't just throw general techniques",
            "dont just throw general techniques",
            "tell me exactly", "be practical", "not theoretical",
            "give me a structure you'd actually implement",
            "give me a structure you would actually implement",
            "before you start", "keep it specific",
            "generic intro", "focus on a concrete project",
            "what you actually did", "why it was impactful",
            "i want a clear set of steps", "go."
        ]

        off_topic_phrases = [
            "let's talk about something else", "lets talk about something else",
            "i don't want this interview", "i dont want this interview",
            "change the topic", "leave this question", "next question please",
            "i am not here for", "i'm not here for"
        ]

        # Direct phrase checks.
        if any(p in clean for p in audio_issue_phrases):
            return "AUDIO_ISSUE"

        if any(p in clean for p in repeat_phrases):
            return "REPEAT_REQUEST"

        if any(p in clean for p in clarification_phrases):
            return "CLARIFICATION_REQUEST"

        if any(p in clean for p in external_prompt_phrases):
            return "EXTERNAL_PROMPT_ECHO"

        if any(p in clean for p in off_topic_phrases):
            return "OFF_TOPIC"

        # Short question-like utterances are clarification, not answers.
        if clean.endswith("?") and len(words) <= 10:
            return "CLARIFICATION_REQUEST"

        # Very short vague utterances should not be scored.
        vague_short = {
            "yes", "no", "okay", "ok", "yeah", "hmm", "um", "uh",
            "what", "why", "how", "about what"
        }
        if clean in vague_short:
            return "CLARIFICATION_REQUEST"

        # Interviewer-instruction style: many imperatives, little candidate ownership.
        instruction_markers = [
            "tell me", "give me", "walk me through", "i want", "don't", "dont",
            "focus on", "be specific", "be practical", "skip"
        ]
        answer_markers = [
            "i built", "i worked", "i used", "i implemented", "i created",
            "i trained", "i evaluated", "my project", "my model", "we built",
            "we used", "python", "machine learning", "model", "dataset",
            "accuracy", "precision", "recall", "api", "deployment"
        ]

        instruction_hits = sum(1 for p in instruction_markers if p in clean)
        answer_hits = sum(1 for p in answer_markers if p in clean)

        if instruction_hits >= 2 and answer_hits == 0:
            return "EXTERNAL_PROMPT_ECHO"

        # If it looks like a technical fragment, let the incomplete transcript
        # gate handle it instead of letting semantic intent misclassify it as
        # repeat/external/off-topic.
        if self._looks_like_incomplete_transcript(transcript, last_question):
            return "ANSWER_ATTEMPT"

        # Semantic fallback for unseen wording.
        # Example: "Sorry, I missed the first part" or
        # "Are you asking about the dataset or the model?"
        if self._should_use_semantic_intent_classifier(transcript):
            return self._semantic_intent_classify(transcript, last_question)

        return "ANSWER_ATTEMPT"



    def _should_use_semantic_intent_classifier(self, transcript: str) -> bool:
        """
        Use LLM intent classifier only for ambiguous utterances.
        This avoids extra latency on normal technical answers.
        """
        text = (transcript or "").strip().lower()
        if not text:
            return False

        words = text.split()
        word_count = len(words)

        # Short utterances are often clarification/audio/off-topic, not real answers.
        if word_count <= 12:
            return True

        # Question-like utterances should be semantically checked.
        if "?" in text:
            return True

        ambiguous_markers = [
            "sorry",
            "not sure",
            "i missed",
            "missed that",
            "say it another way",
            "frame it differently",
            "are you asking",
            "do you mean",
            "which part",
            "which one",
            "what angle",
            "your voice",
            "voice cut",
            "audio",
            "mic",
        ]

        if any(marker in text for marker in ambiguous_markers):
            return True

        # External/coaching style instructions are often longer.
        instruction_markers = [
            "tell me exactly",
            "be specific",
            "keep it specific",
            "don't want",
            "dont want",
            "skip the general",
            "not theoretical",
            "be practical",
            "focus on",
            "walk me through",
        ]

        if any(marker in text for marker in instruction_markers):
            return True

        return False


    def _semantic_intent_classify(self, transcript: str, last_question: str = "") -> str:
        """
        LLM fallback classifier for candidate intent.
        Returns one of:
        ANSWER_ATTEMPT, REPEAT_REQUEST, CLARIFICATION_REQUEST,
        AUDIO_ISSUE, OFF_TOPIC, EXTERNAL_PROMPT_ECHO
        """
        import json
        import re

        allowed = {
            "ANSWER_ATTEMPT",
            "REPEAT_REQUEST",
            "CLARIFICATION_REQUEST",
            "AUDIO_ISSUE",
            "OFF_TOPIC",
            "EXTERNAL_PROMPT_ECHO",
        }

        prompt = f"""
You are an intent classifier for a live AI job interview.

Classify the candidate utterance into exactly one label:

ANSWER_ATTEMPT:
The candidate is trying to answer the interview question, even if weak, incomplete, grammatically poor, or technically shallow.

REPEAT_REQUEST:
The candidate asks to repeat the question or say it again.

CLARIFICATION_REQUEST:
The candidate asks what the question means, what specific model/topic is meant, or asks for explanation.

AUDIO_ISSUE:
The candidate says they cannot hear, audio is unclear, says hello/checking connection, or reports voice/mic issue.

OFF_TOPIC:
The candidate intentionally talks about something unrelated to the interview question.

EXTERNAL_PROMPT_ECHO:
The transcript sounds like an interviewer, coach, ChatGPT, instruction, or prompt telling someone how to answer, not the candidate's own answer.

Current interview question:
{last_question}

Candidate utterance:
{transcript}

Return JSON only:
{{"intent":"LABEL","confidence":0.0}}
""".strip()

        try:
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return only valid JSON. No explanation.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
                max_tokens=60,
            )

            content = response.choices[0].message.content.strip()

            # Extract JSON safely even if model wraps text around it.
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                content = match.group(0)

            data = json.loads(content)
            intent = str(data.get("intent", "ANSWER_ATTEMPT")).strip().upper()
            confidence = float(data.get("confidence", 0))

            if intent in allowed and confidence >= 0.55:
                return intent

        except Exception as e:
            # Never block interview because classifier failed.
            print(f"[IntentClassifier] Semantic fallback failed: {e}")

        return "ANSWER_ATTEMPT"





    def _looks_like_incomplete_transcript(self, transcript: str, last_question: str = "") -> bool:
        """
        Detect partial STT fragments that should not be evaluated yet.
        Example: "For missing", "I would use", "The model was", etc.
        """
        text = (transcript or "").strip()
        if not text:
            return True

        clean = text.strip(" .,!?'\"").lower()
        words = clean.split()
        word_count = len(words)

        # Already handled by intent classifier, but keep safe.
        if word_count <= 2:
            return True

        # Very short fragments often come from STT cutoff.
        # Do not block short but complete clarification phrases because intent gate handles them earlier.
        if word_count <= 4:
            technical_keywords = [
                "python", "model", "dataset", "accuracy", "precision", "recall",
                "missing", "categorical", "scaling", "api", "deploy", "overfitting"
            ]
            # If it is only a tiny technical fragment, it is not enough to score.
            if any(k in clean for k in technical_keywords):
                return True

        # For the intro/project-overview question, require more substance.
        # Vague short fragments like "Worked on a project" should not be scored;
        # they indicate STT captured only the beginning of a longer answer.
        if word_count <= 6:
            last_q = (last_question or "").lower()
            is_intro_question = any(m in last_q for m in [
                "introduce yourself", "project", "worked on",
                "tell me about", "machine learning project",
            ])
            if is_intro_question:
                substance_markers = [
                    "random forest", "xgboost", "classification", "regression",
                    "dataset", "accuracy", "precision", "recall", "f1",
                    "training", "preprocessing", "api", "deploy", "nlp",
                    "neural", "cnn", "lstm", "transformer", "pipeline",
                    "scikit", "sklearn", "pytorch", "tensorflow",
                ]
                if not any(m in clean for m in substance_markers):
                    return True

        # Common unfinished starts.
        unfinished_endings = [
            "i would",
            "i will",
            "i used",
            "i use",
            "i was",
            "i have",
            "i had",
            "for missing",
            "for categorical",
            "for scaling",
            "the model",
            "the dataset",
            "my project",
            "in python",
            "because",
            "and then",
            "so",
            "like",
            "using",
            "with",
            "for",
            "to",
            "by",
        ]

        if clean in unfinished_endings:
            return True

        # If answer ends with connector/preposition, probably cut off.
        last_word = words[-1] if words else ""
        cut_words = {
            "and", "or", "but", "because", "with", "for", "to", "by",
            "using", "like", "then", "so", "when", "where", "which"
        }

        if last_word in cut_words:
            return True

        return False


    def _incomplete_transcript_response(self, transcript: str, last_question: str = "") -> str:
        """Ask candidate to continue/repeat without scoring partial STT fragments."""
        partial = (transcript or "").strip()

        if partial:
            return (
                f"I only caught part of your answer: \"{partial}\". "
                "Please continue your answer clearly and directly."
            )

        return "I could not capture your full answer. Please continue or repeat your answer."



    def _infer_question_domain_for_relevance(self, question: str) -> str:
        """Infer expected answer domain from the current interview question."""
        q = (question or "").lower()

        if any(x in q for x in ["introduce yourself", "project you've worked", "project you worked", "ai or machine learning project"]):
            return "project_overview"

        if any(x in q for x in ["python", "code stays clean", "reusable", "debug", "module", "class", "function", "decorator", "context manager"]):
            return "python"

        if any(x in q for x in ["overfitting", "regularization", "cross-validation", "hyperparameter", "random forest", "training accuracy", "validation"]):
            return "machine_learning"

        if any(x in q for x in ["missing values", "categorical", "scaling", "preprocessing", "impute", "encoding", "feature"]):
            return "data_preprocessing"

        if any(x in q for x in ["accuracy", "precision", "recall", "f1", "confusion matrix", "roc", "auc", "metric"]):
            return "model_evaluation"

        if any(x in q for x in ["nlp", "speech", "text", "tokenization", "embedding", "transcript"]):
            return "nlp_speech_ai"

        if any(x in q for x in ["api", "request", "response", "endpoint", "fastapi", "flask", "error handling"]):
            return "apis_backend"

        if any(x in q for x in ["deploy", "deployment", "latency", "monitor", "production", "logs", "docker"]):
            return "deployment"

        return "unknown"


    def _is_answer_relevant_to_question(self, transcript: str, last_question: str) -> bool:
        """
        Stricter domain relevance guard.
        Blocks obvious wrong-domain answers before evaluation.

        Important:
        - Weak but relevant answers should still be scored.
        - Wrong-topic answers should be redirected without scoring.
        """
        answer = (transcript or "").lower().strip()
        question = (last_question or "").lower().strip()

        if not answer or not question:
            return True

        words = answer.split()

        # Very short fragments are handled by incomplete transcript guard.
        if len(words) < 5:
            return True

        def has_any(items):
            return any(x in answer for x in items)

        def q_has_any(items):
            return any(x in question for x in items)

        # -------------------------
        # Exact-question intent guards
        # -------------------------

        # Python structure question
        if q_has_any(["python", "code stays clean", "reusable", "easy to debug", "structure a small machine learning project"]):
            required = [
                "module", "modules", "folder", "folders", "file", "files",
                "function", "functions", "class", "classes", "package",
                "config", "configuration", "logging", "logger", "test", "tests",
                "debug", "reuse", "reusable", "structure", "separate",
                "data loading", "preprocessing", "training", "evaluation"
            ]

            wrong_only_metric = [
                "accuracy", "precision", "recall", "f1", "confusion matrix",
                "roc", "auc", "false positive", "false negative"
            ]

            if has_any(required):
                return True

            # Metrics-only answer to Python structure question is wrong-domain.
            if has_any(wrong_only_metric):
                return False

            return False

        # Overfitting question
        if q_has_any(["overfitting", "training accuracy", "validation performance", "reduce it"]):
            strong_required = [
                "overfitting",
                "validation",
                "validation score",
                "validation performance",
                "regularization",
                "cross validation",
                "cross-validation",
                "early stopping",
                "dropout",
                "reduce complexity",
                "simpler model",
                "more data",
                "hyperparameter",
                "max depth",
                "pruning",
                "bias",
                "variance",
                "train validation gap",
                "training and validation",
                "training score and validation",
                "training is high",
                "validation is low",
            ]

            python_structure_only = [
                "module", "modules", "folder", "folders", "configuration",
                "separate scripts", "clean code", "reusable", "debugging and reusing",
                "data loading", "project structure", "structuring into modules",
                "scripts for training", "scripts for testing"
            ]

            # If it mainly talks about project/code structure, block it before weak keyword matches.
            if has_any(python_structure_only) and not has_any(strong_required):
                return False

            # "training" alone is NOT enough for overfitting relevance.
            if has_any(strong_required):
                return True

            return False

        # Data preprocessing question
        if q_has_any([
            "missing values", "categorical features", "scaling", "before training",
            "preprocessing", "preprocess", "imputation", "impute", "median", "mean",
            "categorical", "encoding", "one-hot", "one hot", "one high", "won hot",
            "standard scaling", "min-max", "numeric features", "preprocessing steps"
        ]):
            required = [
                "missing", "impute", "imputation", "mean", "median", "mode",
                "categorical", "encoding", "one hot", "one-hot", "one high", "won hot",
                "label encoding", "scaling", "standard scaler", "standardscaler", "standard scale",
                "normalize", "normalization", "outlier", "feature", "features", "min-max"
            ]

            api_deploy_only = [
                "fastapi", "api", "endpoint", "request", "response",
                "json", "deployment", "deploy", "docker", "latency"
            ]

            if has_any(required):
                return True

            if has_any(api_deploy_only):
                return False

            return False

        # Model evaluation question
        if q_has_any(["accuracy", "precision", "recall", "f1", "confusion matrix", "evaluation metrics"]):
            required = [
                "accuracy", "precision", "recall", "f1", "f1-score",
                "confusion matrix", "roc", "auc", "false positive",
                "false negative", "metric", "imbalanced", "classification report"
            ]

            if has_any(required):
                return True

            return False

        # NLP / speech preprocessing question
        if q_has_any(["speech", "nlp", "text", "preprocessing steps", "sending text to the model"]):
            required = [
                "text", "nlp", "speech", "audio", "transcript", "token",
                "tokenization", "embedding", "lowercase", "punctuation",
                "stop words", "lemmatize", "stemming", "clean", "noise"
            ]

            if has_any(required):
                return True

            return False

        # API question
        if q_has_any(["api", "request", "response", "error-handling", "error handling", "expose a trained"]):
            required = [
                "api", "endpoint", "fastapi", "flask", "request", "response",
                "json", "input validation", "validation", "error handling",
                "exception", "status code", "route", "prediction"
            ]

            if has_any(required):
                return True

            return False

        # Deployment question
        if q_has_any(["deploy", "deployment", "latency", "monitor", "performance after deployment"]):
            required = [
                "deploy", "deployment", "docker", "container", "server",
                "cloud", "latency", "monitor", "logs", "logging",
                "error", "metrics", "performance", "production",
                "prometheus", "grafana", "ci/cd", "pipeline"
            ]

            if has_any(required):
                return True

            return False

        # Debugging pipeline question
        if q_has_any(["debug", "poor results", "data, preprocessing, model, or evaluation"]):
            required = [
                "debug", "data", "preprocessing", "model", "evaluation",
                "metrics", "logs", "distribution", "missing", "bias",
                "training", "validation", "pipeline"
            ]

            if has_any(required):
                return True

            return False

        # Project overview should be broad.
        if q_has_any(["introduce yourself", "project", "worked on", "showcases your ai", "machine learning skills"]):
            required = [
                "project", "built", "worked", "model", "dataset", "classification",
                "prediction", "detection", "random forest", "xgboost",
                "machine learning", "ai", "trained", "evaluated"
            ]

            if has_any(required):
                return True

            return False

        # Unknown question type: don't block.
        return True


    def _domain_relevance_redirect_response(self, last_question: str) -> str:
        """Redirect candidate back to the same question without scoring."""
        return (
            "Let's stay on the current interview question. "
            "Your last response did not clearly answer what I asked. "
            f"Please answer this directly: {last_question}"
        )



    def _intent_redirect_response(self, intent: str, transcript: str, last_question: str = "") -> str:
        """Generate a no-score redirect based on classified candidate intent."""
        last_question = (last_question or "").strip()

        if intent == "REPEAT_REQUEST":
            return f"Sure, I'll repeat the question. {self._short_repeat_question(last_question)}"

        if intent == "AUDIO_ISSUE":
            return f"No problem, I'll repeat it clearly. {self._short_repeat_question(last_question)}"

        if intent == "CLARIFICATION_REQUEST":
            t_clean = (transcript or "").lower()
            if any(phrase in t_clean for phrase in ["understand", "not clear", "unclear"]):
                return f"Sure, I'll repeat the question. {self._short_repeat_question(last_question)}"
            return (
                "Good question. I'm asking you to answer the current interview question directly. "
                f"Here it is again: {self._short_repeat_question(last_question)}"
            )

        if intent == "OFF_TOPIC":
            return (
                "Let's stay focused on the interview. "
                f"Please answer this question directly: {self._short_repeat_question(last_question)}"
            )

        if intent == "EXTERNAL_PROMPT_ECHO":
            return (
                "I may have captured an instruction or external prompt instead of your answer. "
                f"Please answer the current interview question directly: {self._short_repeat_question(last_question)}"
            )

        return f"Please answer the current interview question directly: {self._short_repeat_question(last_question)}"



    def _is_clarification_request(self, transcript: str) -> bool:
        """
        Detect valid candidate clarification/repeat requests.
        These should NOT be scored, but should be answered politely.
        """
        t = (transcript or "").strip().lower()
        if not t:
            return False

        clarification_markers = [
            "repeat the question",
            "can you repeat",
            "could you repeat",
            "please repeat",
            "say that again",
            "come again",
            "i didn't understand",
            "i did not understand",
            "what do you mean",
            "what does that mean",
            "can you explain",
            "could you explain",
            "explain the question",
            "clarify the question",
            "what is meant by",
            "what do you mean by",
        ]

        return any(marker in t for marker in clarification_markers)


    def _is_external_prompt_echo(self, transcript: str, last_question: str = "") -> bool:
        """
        Detect external interviewer/ChatGPT prompt, bot prompt echo, or wrong-speaker capture.
        These should NOT be scored as candidate answers.
        """
        import re

        t = (transcript or "").strip().lower()
        q = (last_question or "").strip().lower()

        if not t:
            return False

        words = t.split()
        if len(words) < 5:
            return False

        external_prompt_markers = [
            "i'm not here for pleasantries",
            "i am not here for pleasantries",
            "don't waste time on fluff",
            "dont waste time on fluff",
            "just give me one ai",
            "just give me one ml",
            "what problem did you tackle",
            "what did you actually achieve",
            "give me the real impact",
            "tell me about one ai",
            "tell me about one machine learning",
            "can you start by introducing yourself",
            "start by introducing yourself",
            "your reality check",
            "if you skip these",

            # External interviewer / coaching / off-topic style phrases
            "let's get serious",
            "lets get serious",
            "i'm here to challenge you",
            "i am here to challenge you",
            "i hear you",
            "trust me",
            "that's on you",
            "thats on you",
            "you're asking for trouble",
            "you are asking for trouble",
            "you're setting yourself up",
            "you are setting yourself up",
            "you're failing",
            "you are failing",
            "don't be lazy",
            "dont be lazy",
            "if you're blindly",
            "if you are blindly",
            "garbage output",
            "garbage in garbage out",
            "raw truth",
            "bottom line",
            "in short",
        ]

        if any(marker in t for marker in external_prompt_markers):
            return True

        # Detect if candidate transcript is mostly the same as the question.
        # This catches bot/question echo from speaker or external interviewer.
        if q:
            t_words = set(re.findall(r"[a-zA-Z]+", t))
            q_words = set(re.findall(r"[a-zA-Z]+", q))

            if len(t_words) >= 6 and len(q_words) >= 6:
                overlap = len(t_words & q_words) / max(1, len(q_words))
                if overlap >= 0.70:
                    return True

        return False


    def _clarification_response(self, transcript: str, last_question: str = "") -> str:
        """
        Return a helpful clarification without scoring the candidate.
        """
        t = (transcript or "").strip().lower()
        last_question = (last_question or "").strip()

        if "repeat" in t or "say that again" in t or "come again" in t:
            return "Sure, I'll repeat the question. " + (last_question or "Please tell me about one AI or machine learning project you worked on.")

        if "preprocessing" in t:
            return "Preprocessing means cleaning and preparing data before training, such as handling missing values, encoding categories, and scaling numbers. Now please answer the question."

        if "model evaluation" in t or "evaluation" in t:
            return "Model evaluation means checking how well your model performs using metrics like accuracy, precision, recall, F1-score, or confusion matrix. Now please answer the question."

        if "deployment" in t or "deploy" in t:
            return "Deployment means making your model available for real use, usually through an API or server, and monitoring latency, errors, and performance. Now please answer the question."

        if "overfitting" in t:
            return "Overfitting means the model performs well on training data but poorly on unseen data. Now please answer how you would detect and reduce it."

        return "Sure. I?m asking this: " + (last_question or "Please tell me about one AI or machine learning project you worked on.")


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