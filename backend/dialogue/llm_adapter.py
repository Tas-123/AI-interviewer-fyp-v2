"""
LLM Adapter — Handles all communication with Groq API.
Generates interview questions based on the current action and conversation context.
"""


NATURAL_INTERVIEWER_STYLE_RULES = """
NATURAL INTERVIEWER STYLE RULES:
- Sound like a calm senior technical interviewer, not a robotic questionnaire.
- Keep the same domain and intent, but vary the wording naturally.
- Ask only ONE question at a time.
- Use short, varied transitions (e.g. "Alright —", "Building on that —",
  "Suppose…", "In a real project…"). Prefer no opener when the question already stands alone.
  Avoid opening every question with "Let's talk/move…".
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

DEFAULT_ROLE_TITLE = "technical interview"


def resolve_role_title(context=None, resume_data: dict | None = None) -> str:
    """Active interview display title — never force Junior AI Engineer."""
    if context is not None:
        rd = getattr(context, "resume_data", None) or {}
        title = (
            rd.get("role")
            or getattr(getattr(context, "role_config", None), "display_title", None)
            or getattr(context, "role_title", None)
        )
        if title and str(title).strip():
            return str(title).strip()
    if resume_data:
        title = resume_data.get("role")
        if title and str(title).strip():
            return str(title).strip()
    return DEFAULT_ROLE_TITLE

# Fallback seeds for Junior AI Engineer (also used when context has no role seeds).
from core.domain_packs import all_seeds, all_spoken_cores

DOMAIN_QUESTION_SEEDS: dict[str, str] = all_seeds()
# Keep AI-specific wording for classic AI domains (matches prior behavior).
try:
    from core.role_templates import build_junior_ai_engineer

    _ai = build_junior_ai_engineer()
    DOMAIN_QUESTION_SEEDS.update(_ai.seeds)
except Exception:
    pass


def _seeds_from_context(context) -> dict[str, str]:
    seeds = getattr(context, "domain_seeds", None)
    if isinstance(seeds, dict) and seeds:
        return seeds
    return DOMAIN_QUESTION_SEEDS


def _cores_from_context(context) -> dict[str, str]:
    cores = getattr(context, "domain_spoken_cores", None)
    if isinstance(cores, dict) and cores:
        return cores
    return all_spoken_cores()


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
            question = self._ensure_spoken_question(
                question, context, domain="project_overview"
            )
            self._commit_active_question(context, question, "project_overview")
            return question

        if action_type == "followup":
            question = self._generate_followup(action, context)
            domain = action.get("domain", getattr(context, "current_domain", ""))
            question = self._ensure_spoken_question(question, context, domain=domain)
            self._commit_active_question(context, question, domain)
            return question

        topic = action.get("topic", "")
        if topic == "behavioral":
            question = self._generate_behavioral(action, context)
            question = self._ensure_spoken_question(
                question, context, domain="behavioral_ownership"
            )
            self._commit_active_question(context, question, "behavioral_ownership")
            return question

        question = self._generate_technical(action, context)
        domain = action.get("domain", topic)
        question = self._ensure_spoken_question(question, context, domain=domain)
        self._commit_active_question(context, question, domain)
        return question

    def _domain_seed_fallback(self, context, domain: str = "") -> str:
        """Role pack seed/core when LLM question generation fails."""
        dkey = (domain or getattr(context, "current_domain", "") or "").strip().lower()
        seeds = _seeds_from_context(context)
        cores = _cores_from_context(context)
        text = (cores.get(dkey) or seeds.get(dkey) or "").strip()
        if text:
            return text
        return (
            "Please explain one practical technical approach for this topic, "
            "including the steps you would take and how you would validate it."
        )

    def _ensure_spoken_question(self, question: str, context, *, domain: str = "") -> str:
        q = (question or "").strip()
        if q and not q.startswith("[Error generating"):
            return q
        fallback = self._domain_seed_fallback(context, domain)
        logger.error(
            "Question generation failed; using domain seed fallback for %s",
            domain or "unknown",
        )
        return fallback

    def _commit_active_question(self, context, question: str, domain: str = "") -> None:
        if not question or str(question).startswith("[Error"):
            return
        if hasattr(context, "set_active_question"):
            dkey = (domain or "").strip().lower()
            intent = _seeds_from_context(context).get(
                dkey,
                str(domain or "").replace("_", " "),
            )
            clipped = self._clip_spoken_question(str(question))
            context.set_active_question(clipped or question, domain_intent=intent)

    # ════════════════════════════════════════════════════════════
    #  Private generation methods
    # ════════════════════════════════════════════════════════════

    def _generate_intro(self, context):
        """Generate a warm professional greeting."""
        skills_list = list(getattr(context, "skills", []) or [])[:5]
        skills_str = ", ".join(skills_list) if skills_list else "general"
        experience = context.resume_data.get("experience", "not specified")
        role_title = resolve_role_title(context)
        name = context.resume_data.get("name", "Candidate")
        profile_source = context.resume_data.get("profile_source", "default")
        projects = context.resume_data.get("projects") or []
        project_hint = ", ".join(str(p) for p in projects[:2]) if projects else ""

        prompt = INTRO_SYSTEM_PROMPT.format(
            role_title=role_title,
            skills=skills_str,
            experience=experience,
        )
        prompt += f"""

Session context:
- Candidate name: {name}
- Target role: {role_title}
- Profile source: {profile_source}
- Projects from resume: {project_hint or "none listed"}
- You MUST name the interview as "{role_title}" — never substitute a different job title.
- If profile_source is resume and Skills is not "general", briefly name ONE concrete skill or project from the Skills/Projects lists above — never invent others.
- If profile_source is default, explain this is a structured {role_title} practice interview without inventing a personal skill list.
- Ask exactly ONE opening question (introduce yourself + one project or technical experience).
"""
        return self._call_llm(prompt)

    def _generate_technical(self, action, context):
        """Generate a technical question on a specific topic."""
        topic = action.get("topic", "general")
        domain = action.get("domain", topic)
        difficulty = action.get("difficulty", "medium")
        seed = _seeds_from_context(context).get(domain, "")
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
                            domain,
                            bank_question,
                            variety_seed=variety,
                            replace_with_core=False,
                            cores=_cores_from_context(context),
                        )
                    )
                    if candidate and not is_semantic_duplicate(
                        candidate, context.question_history
                    ):
                        return candidate

        # 2) Prefer naturalized domain seed (short, deterministic, voice-friendly).
        if action.get("type") == "ask" and seed:
            candidate = self._clip_spoken_question(
                _naturalize_static_question(
                    domain,
                    seed,
                    variety_seed=variety,
                    cores=_cores_from_context(context),
                )
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

        role_title = resolve_role_title(context)
        system_prompt = TECHNICAL_SYSTEM_PROMPT.format(
            role_title=role_title,
            topic=topic,
            difficulty=difficulty,
        )

        system_prompt += f"""
        
Interview policy:
- You are interviewing for a {role_title} role.
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
                _naturalize_static_question(
                    domain,
                    seed,
                    variety_seed=variety,
                    cores=_cores_from_context(context),
                )
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
            # Prefer skills that appear in domain evidence when available.
            evidence_l = " ".join(str(e).lower() for e in evidence)
            domain_skills = [
                s for s in skills if str(s).lower() in evidence_l
            ] if evidence else []
            show = (domain_skills or skills)[:6]
            lines.append("- Skills: " + ", ".join(str(s) for s in show))
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
You are a professional live voice interviewer for a {resolve_role_title(context)} role.

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
                f"{BEHAVIORAL_SYSTEM_PROMPT.format(role_title=resolve_role_title(context))}\n\n"
                f"Focus this question on the category: {category}\n\n"
            )
        else:
            full_prompt = (
                f"{BEHAVIORAL_SYSTEM_PROMPT.format(role_title=resolve_role_title(context))}\n\n"
            )

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
            role_title=resolve_role_title(context),
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
    domain: str,
    question: str,
    variety_seed: int = 0,
    *,
    replace_with_core: bool = True,
    cores: dict[str, str] | None = None,
) -> str:
    """
    Lightly naturalize fixed blueprint questions without changing their intent.

    When replace_with_core is True (seed path), swap in the fair fixed core for
    the domain. When False (resume/bank path), keep the question text and only
    optionally add a short opener.
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

    # Prefer role-config cores; fall back to shared domain pack spoken cores.
    if isinstance(cores, dict) and cores:
        core_map = dict(cores)
    else:
        core_map = all_spoken_cores()
        # Preserve classic AI wording for shared domain ids when no role context.
        try:
            from core.role_templates import build_junior_ai_engineer

            core_map.update(build_junior_ai_engineer().spoken_cores)
        except Exception:
            pass

    if replace_with_core:
        core = core_map.get(d)
        if not core:
            return q
        spoken = core
    else:
        spoken = q

    # Prefer empty openers so interviews sound less scripted.
    openers = (
        "",
        "",
        "",
        "Alright — ",
        "Building on that — ",
    )
    # Deterministic rotation from seed (turn index) so tests stay stable for seed=0.
    opener = openers[int(variety_seed) % len(openers)]
    return f"{opener}{spoken}".strip()


