"""
LLM Adapter — Handles all communication with Groq API.
Generates interview questions based on the current action and conversation context.
"""


NATURAL_INTERVIEWER_STYLE_RULES = """
NATURAL INTERVIEWER STYLE RULES:
- Sound like a calm senior technical interviewer, not a robotic questionnaire.
- Keep the same domain and intent, but vary the wording naturally.
- Ask only ONE question at a time.
- Use short, varied transitions (e.g. "Alright —", "Next up:", "Building on that —",
  "Suppose…", "In a real project…"). Avoid opening every question with "Let's talk/move…".
- Avoid repeating the exact same wording from previous questions.
- Avoid long greetings after the first question.
- Avoid overexplaining the question.
- For technical domains, ask practical scenario-based questions.
- Do not use STAR wording for technical domains.
- Keep questions concise and voice-friendly.
"""



import logging
import os
from dotenv import load_dotenv
from groq import Groq
from core.config import settings
from dialogue.output_sanitizer import sanitize_interviewer_output
from dialogue.question_dedup import is_semantic_duplicate
from dialogue.prompts import (
    BEHAVIORAL_SYSTEM_PROMPT,
    TECHNICAL_SYSTEM_PROMPT,
    INTRO_SYSTEM_PROMPT,
    FOLLOWUP_SYSTEM_PROMPT,
)


logger = logging.getLogger(__name__)

# Intent seeds / fallbacks for Junior AI Engineer blueprint domains.
DOMAIN_QUESTION_SEEDS: dict[str, str] = {
    "project_overview": (
        "Briefly explain one AI or machine learning project you worked on. "
        "What problem did it solve, what did you build, and what was the result?"
    ),
    "python": (
        "In Python, how would you structure a small machine learning project so the "
        "code stays clean, reusable, and easy to debug?"
    ),
    "machine_learning": (
        "How would you detect overfitting in a machine learning model, and what "
        "steps would you take to reduce it?"
    ),
    "data_preprocessing": (
        "How would you handle missing values, categorical features, and scaling "
        "before training a machine learning model?"
    ),
    "model_evaluation": (
        "For a classification model, how would you choose evaluation metrics such as "
        "accuracy, precision, recall, F1-score, and confusion matrix?"
    ),
    "nlp_speech_ai": (
        "If you are building a speech or NLP-based AI system, what preprocessing "
        "steps would you apply before sending text to the model?"
    ),
    "apis_backend": (
        "How would you expose a trained AI model through an API, and what request, "
        "response, and error-handling details would you include?"
    ),
    "deployment": (
        "What steps would you take to deploy a small AI model and monitor its "
        "latency, errors, and performance after deployment?"
    ),
    "debugging_problem_solving": (
        "If your AI pipeline gives poor results, how would you debug whether the "
        "issue is in the data, preprocessing, model, or evaluation?"
    ),
    "behavioral_ownership": (
        "Tell me about a time you took ownership of a technical problem. "
        "What did you do, and what was the outcome?"
    ),
}


class LLMAdapter:

    def __init__(self):
        load_dotenv()
        api_key = settings.groq_api_key
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing. Add it to your .env file.")
        self.client = Groq(api_key=api_key)
        self.model = settings.groq_model
        self.question_selector = None

    def generate(self, action, context):
        """
        Generate a question based on the action dict from DecisionEngine.
        Uses conversation history from context to avoid repeating questions.
        """
        action_type = action.get("type", "ask")

        if action_type == "closing":
            return "Thank you for your time. This concludes the interview."

        if action_type == "intro":
            question = self._generate_intro(context)
            self._commit_active_question(context, question, "project_overview")
            return question

        if action_type == "followup":
            question = self._generate_followup(action, context)
            domain = action.get("domain", getattr(context, "current_domain", ""))
            self._commit_active_question(context, question, domain)
            return question

        topic = action.get("topic", "")
        if topic == "behavioral":
            question = self._generate_behavioral(action, context)
            self._commit_active_question(context, question, "behavioral_ownership")
            return question

        question = self._generate_technical(action, context)
        domain = action.get("domain", topic)
        self._commit_active_question(context, question, domain)
        return question

    def _commit_active_question(self, context, question: str, domain: str = "") -> None:
        if not question or str(question).startswith("[Error"):
            return
        if hasattr(context, "set_active_question"):
            intent = DOMAIN_QUESTION_SEEDS.get(
                (domain or "").strip().lower(),
                str(domain or "").replace("_", " "),
            )
            clipped = self._clip_spoken_question(str(question))
            context.set_active_question(clipped or question, domain_intent=intent)

    # ════════════════════════════════════════════════════════════
    #  Private generation methods
    # ════════════════════════════════════════════════════════════

    def _generate_intro(self, context):
        """Generate a warm professional greeting."""
        skills_str = ", ".join(context.skills) if context.skills else "general"
        experience = context.resume_data.get("experience", "not specified")
        role_title = context.resume_data.get("role", "Junior AI Engineer")
        name = context.resume_data.get("name", "Candidate")
        profile_source = context.resume_data.get("profile_source", "default")
        projects = context.resume_data.get("projects") or []
        project_hint = ", ".join(str(p) for p in projects[:2]) if projects else ""

        prompt = INTRO_SYSTEM_PROMPT.format(
            skills=skills_str,
            experience=experience,
        )
        prompt += f"""

Session context:
- Candidate name: {name}
- Target role: {role_title}
- Profile source: {profile_source}
- Projects from resume: {project_hint or "none listed"}
- If profile_source is resume, you MUST briefly name one concrete skill or project from their resume in the greeting before asking them to introduce themselves.
- If profile_source is default, explain this is a structured {role_title} practice interview.
- Ask exactly ONE opening question (introduce yourself + one project).
"""
        return self._call_llm(prompt)

    def _generate_technical(self, action, context):
        """Generate a technical question on a specific topic."""
        topic = action.get("topic", "general")
        domain = action.get("domain", topic)
        difficulty = action.get("difficulty", "medium")
        seed = DOMAIN_QUESTION_SEEDS.get(domain, "")
        variety = len(getattr(context, "question_history", []) or [])

        # 1) On-domain resume question (never role_specific bank for technical domains).
        if action.get("type") == "ask":
            selector = getattr(context, "question_selector", None) or self.question_selector
            if selector:
                bank_question = selector.select_for_domain(
                    domain,
                    asked_questions=context.question_history,
                )
                if bank_question:
                    candidate = self._clip_spoken_question(
                        _naturalize_static_question(
                            domain, bank_question, variety_seed=variety
                        )
                    )
                    if candidate and not is_semantic_duplicate(
                        candidate, context.question_history
                    ):
                        return candidate

        # 2) Prefer naturalized domain seed (short, deterministic, voice-friendly).
        if action.get("type") == "ask" and seed:
            candidate = self._clip_spoken_question(
                _naturalize_static_question(domain, seed, variety_seed=variety)
            )
            if candidate and not is_semantic_duplicate(
                candidate, context.question_history
            ):
                return candidate

            # 3) Bounded LLM only when seed was already used / duplicate.
            generated = self._generate_bounded_domain_question(
                context,
                domain=domain,
                seed=seed,
                difficulty=difficulty,
            )
            if generated and not is_semantic_duplicate(
                generated, context.question_history
            ):
                return generated

            # 4) Seed fallback (even if duplicate — better than empty).
            if candidate:
                return candidate

        system_prompt = TECHNICAL_SYSTEM_PROMPT.format(
            topic=topic,
            difficulty=difficulty,
        )

        system_prompt += f"""
        
Interview policy:
- You are interviewing for a {context.resume_data.get("role", "Junior AI Engineer")} role.
- Current required domain: {domain}.
- Domain intent seed: {seed or topic}
- Ask exactly ONE focused question for this domain.
- Maximum ~25 words, one sentence, one question mark.
- Keep it practical and junior-level.
- Do not ask multiple questions at once.
- Do not keep drilling previous domains unless this is explicitly a follow-up.
- Avoid repeating previous questions.
- Prefer questions that reveal practical understanding, not textbook memorization.
"""

        resume_block = self._resume_domain_block(context, domain)
        if resume_block:
            system_prompt += f"\n\n{resume_block}\n"

        messages = self._build_history_text(context)
        recent_qa = self._recent_qa_block(context)
        full_prompt = system_prompt
        if recent_qa:
            full_prompt += (
                f"\n\n{recent_qa}\n"
                "When useful, briefly reference something specific the candidate said "
                "(e.g. a tool or approach) — do not repeat their answer."
            )
        if messages:
            full_prompt += (
                f"\n\nPrevious questions asked in this interview:\n{messages}\n\n"
                f"Now ask a NEW question."
            )
        else:
            full_prompt += "\n\nNow ask a NEW question."

        text = self._call_llm(full_prompt)
        limited = self._enforce_voice_question_limits(text or "")
        if limited:
            return limited
        if seed:
            return self._clip_spoken_question(
                _naturalize_static_question(domain, seed, variety_seed=variety)
            )
        return self._clip_spoken_question(text or "")

    def _resume_domain_block(self, context, domain: str) -> str:
        profile_source = getattr(context, "profile_source", None) or context.resume_data.get(
            "profile_source", "default"
        )
        if profile_source != "resume":
            return ""

        by_domain = getattr(context, "resume_by_domain", None) or context.resume_data.get(
            "resume_by_domain"
        ) or {}
        evidence = list(by_domain.get(domain, []) or [])
        projects = context.resume_data.get("projects") or []
        skills = list(getattr(context, "skills", []) or [])

        lines = ["Resume personalization (prefer this evidence when asking):"]
        if evidence:
            lines.append("- Domain evidence: " + "; ".join(str(e) for e in evidence[:4]))
        if projects and domain in ("project_overview", "nlp_speech_ai", "machine_learning"):
            lines.append("- Projects: " + "; ".join(str(p) for p in projects[:3]))
        if skills:
            lines.append("- Skills: " + ", ".join(str(s) for s in skills[:8]))
        if len(lines) == 1:
            return ""
        lines.append(
            "If resume evidence exists for this domain, ask about THAT evidence. "
            "Otherwise stay on the domain seed intent."
        )
        return "\n".join(lines)

    def _generate_bounded_domain_question(
        self,
        context,
        *,
        domain: str,
        seed: str,
        difficulty: str = "medium",
    ) -> str | None:
        """LLM-generate one domain question constrained by seed + resume."""
        resume_block = self._resume_domain_block(context, domain)
        recent_qa = self._recent_qa_block(context)
        history = self._build_history_text(context)

        prompt = f"""
You are a professional live voice interviewer for a Junior AI Engineer role.

Generate exactly ONE spoken interview question.

Hard constraints:
- Domain id: {domain}
- Keep the SAME learning intent as this seed (do not change topic):
  {seed}
- Difficulty: {difficulty}
- Ask only one question (exactly one question mark).
- Maximum 25 words. One short sentence. Voice-friendly.
- Junior-level, practical.
- No coaching, no hints, no answer examples.
- Do not use markdown or bullet lists.
- Do not stack multiple questions.

{resume_block}

{recent_qa}

Previous questions:
{history or "(none yet)"}

Return ONLY the spoken question.
""".strip()

        text = self._call_llm(prompt)
        if not text or text.startswith("[Error"):
            return None
        cleaned = sanitize_interviewer_output(text).strip()
        return self._enforce_voice_question_limits(cleaned)

    @staticmethod
    def _enforce_voice_question_limits(text: str, max_words: int = 28) -> str | None:
        """Reject overlong / multi-question LLM asks so callers can fall back to seed."""
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        if cleaned.count("?") > 1:
            return None
        words = cleaned.split()
        if len(words) < 5 or len(words) > max_words:
            return None
        return cleaned

    @staticmethod
    def _clip_spoken_question(text: str, max_words: int = 28) -> str:
        """Soft-cap spoken primaries: one ?, ~max_words (keeps text for seed paths)."""
        cleaned = (text or "").strip()
        if not cleaned:
            return cleaned
        if cleaned.count("?") > 1:
            cleaned = cleaned.split("?", 1)[0].strip() + "?"
        words = cleaned.split()
        if len(words) > max_words:
            cleaned = " ".join(words[:max_words]).rstrip(",;: ")
            if "?" not in cleaned:
                cleaned = cleaned.rstrip(".!") + "?"
        return cleaned

    def _generate_behavioral(self, action, context):
        """Generate a behavioral question, optionally targeting a category."""
        category = action.get("category", None)

        # Build conversation context so LLM avoids repeating
        messages = self._build_history_text(context)
        recent_qa = self._recent_qa_block(context)

        if category:
            full_prompt = (
                f"{BEHAVIORAL_SYSTEM_PROMPT}\n\n"
                f"Focus this question on the category: {category}\n\n"
            )
        else:
            full_prompt = f"{BEHAVIORAL_SYSTEM_PROMPT}\n\n"

        if recent_qa:
            full_prompt += (
                f"{recent_qa}\n"
                "When useful, briefly reference something specific the candidate said.\n\n"
            )

        if messages:
            full_prompt += (
                f"Previous questions asked in this interview:\n{messages}\n\n"
                f"Now ask a NEW question that has not been asked before."
            )
        else:
            full_prompt += "Ask your first behavioral question."

        return self._call_llm(full_prompt)

    def _generate_followup(self, action, context):
        """Generate a simpler follow-up question on the same topic."""
        topic = action.get("topic", "general")
        domain = action.get("domain", topic)
        difficulty = action.get("difficulty", "easy")

        prompt = FOLLOWUP_SYSTEM_PROMPT.format(
            topic=topic,
            difficulty=difficulty,
        )

        recent_qa = self._recent_qa_block(context)
        if recent_qa:
            prompt += f"\n\n{recent_qa}\n"

        prompt += f"""
        
Follow-up policy:
- You are allowed only ONE follow-up for this domain.
- Current domain: {domain}.
- Ask one short, direct follow-up based on the candidate's weak answer above.
- Reference a concrete detail from their answer when possible.
- Do not start a long chain of follow-ups.
- Do not ask multiple questions at once.
"""
        return self._call_llm(prompt)

    # ════════════════════════════════════════════════════════════
    #  Helpers
    # ════════════════════════════════════════════════════════════

    # Sliding window: keep anti-repeat history bounded for long interviews.
    HISTORY_QUESTION_WINDOW = 6
    HISTORY_MAX_CHARS = 1800
    RECENT_QA_PAIRS = 3
    RECENT_QA_MAX_CHARS = 1200

    def _recent_qa_block(self, context) -> str:
        """Compact recent Q&A memory for answer-aware question generation."""
        if hasattr(context, "format_recent_qa_for_prompt"):
            return context.format_recent_qa_for_prompt(
                n=self.RECENT_QA_PAIRS,
                max_chars=self.RECENT_QA_MAX_CHARS,
            )
        return ""

    def _build_history_text(self, context):
        """Build a bounded text summary of previously asked questions."""
        history = list(getattr(context, "question_history", None) or [])
        if not history:
            return ""

        window = history[-self.HISTORY_QUESTION_WINDOW :]
        # Keep original interview numbering for readability.
        start_idx = len(history) - len(window) + 1
        lines = [f"{i}. {q}" for i, q in enumerate(window, start_idx)]
        text = "\n".join(lines)
        if self.HISTORY_MAX_CHARS > 0 and len(text) > self.HISTORY_MAX_CHARS:
            text = text[: self.HISTORY_MAX_CHARS - 3].rstrip() + "..."
        return text

    def _call_llm(self, prompt):
        """Make a single call to Groq with one retry on failure."""
        from dialogue.groq_debug_log import log_groq_exchange

        log_groq_exchange("GROQ_QUESTION_PROMPT", prompt)
        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a professional live voice interviewer. "
                                "Never coach, hint, or provide example answers. "
                                "Return only the spoken response. No markdown, no bullets, no headings."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.4,
                    max_tokens=120,
                )

                text = response.choices[0].message.content.strip()
                text = sanitize_interviewer_output(text)
                log_groq_exchange("GROQ_QUESTION_REPLY", text)

                if text and len(text) > 5:
                    return text

                if attempt == 0:
                    logger.warning("Empty/short response on attempt 1, retrying...")
                    continue

                return text if text else "[Error generating question. Please try again.]"

            except Exception as e:
                if attempt == 0:
                    logger.warning("Attempt 1 failed: %s, retrying...", e)
                    continue

                logger.error("Groq LLM error: %s", e)
                return "[Error generating question. Please try again.]"

        return "[Error generating question. Please try again.]"




def _naturalize_static_question(
    domain: str, question: str, variety_seed: int = 0
) -> str:
    """
    Lightly naturalize fixed blueprint questions without changing their intent.

    Phase 6: rotate short transitions so consecutive interviews don't all
    open with the same \"Let's talk / move…\" frame. Core ask stays fixed.
    """
    d = (domain or "").lower().strip()
    q = (question or "").strip()

    if not q:
        return q

    # Avoid changing already conversational follow-ups.
    lower_q = q.lower()
    if lower_q.startswith(
        (
            "you mentioned",
            "can you walk me through",
            "suppose",
            "in a real",
            "tell me about a time",
            "building on",
            "alright",
            "next up",
            "shifting",
        )
    ):
        return q

    # Fixed cores (fairness / coverage). Transitions rotate separately.
    cores = {
        "python": (
            "In a small ML project, how would you organize the code so it stays "
            "clean, reusable, and easy to debug?"
        ),
        "machine_learning": (
            "Suppose your training score is high but validation performance drops. "
            "How would you detect overfitting, and what would you do to reduce it?"
        ),
        "data_preprocessing": (
            "Before training a model, how would you handle missing values, "
            "categorical features, and scaling?"
        ),
        "model_evaluation": (
            "For a classification model, how would you choose between accuracy, "
            "precision, recall, F1-score, and the confusion matrix?"
        ),
        "nlp_speech_ai": (
            "Suppose you're building a speech or NLP-based AI system. "
            "What preprocessing would you apply before sending the text to the model?"
        ),
        "apis_backend": (
            "Once your model is trained and ready, how would you expose it through "
            "an API, including request, response, and error handling?"
        ),
        "deployment": (
            "How would you deploy a small AI model and monitor latency, errors, "
            "and model performance after release?"
        ),
        "debugging_problem_solving": (
            "Suppose your AI pipeline starts giving poor results. How would you "
            "debug whether the issue is in the data, preprocessing, model, or evaluation?"
        ),
        "behavioral_ownership": (
            "Tell me about a time you took ownership of a technical problem. "
            "What did you do, and what was the outcome?"
        ),
        "project_overview": (
            "Briefly explain one AI or machine learning project you worked on. "
            "What problem did it solve, what did you build, and what was the result?"
        ),
    }

    core = cores.get(d)
    if not core:
        return q

    openers = (
        "",
        "Alright — ",
        "Next up: ",
        "Building on that — ",
        "Shifting topics briefly — ",
    )
    # Deterministic rotation from seed (turn index) so tests stay stable for seed=0.
    opener = openers[int(variety_seed) % len(openers)]
    return f"{opener}{core}".strip()


