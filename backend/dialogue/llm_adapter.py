"""
LLM Adapter — Handles all communication with Groq API.
Generates interview questions based on the current action and conversation context.
"""


NATURAL_INTERVIEWER_STYLE_RULES = """
NATURAL INTERVIEWER STYLE RULES:
- Sound like a calm senior technical interviewer, not a robotic questionnaire.
- Keep the same domain and intent, but vary the wording naturally.
- Ask only ONE question at a time.
- Use short transitions like: "Let's move to...", "Now let's talk about...", "Suppose...", "In a real project..."
- Avoid repeating the exact same wording from previous questions.
- Avoid long greetings after the first question.
- Avoid overexplaining the question.
- For technical domains, ask practical scenario-based questions.
- Do not use STAR wording for technical domains.
- Keep questions concise and voice-friendly.
"""



import os
from dotenv import load_dotenv
from groq import Groq
from dialogue.output_sanitizer import sanitize_interviewer_output
from dialogue.prompts import (
    BEHAVIORAL_SYSTEM_PROMPT,
    TECHNICAL_SYSTEM_PROMPT,
    INTRO_SYSTEM_PROMPT,
    FOLLOWUP_SYSTEM_PROMPT,
)


class LLMAdapter:

    def __init__(self):
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing. Add it to your .env file.")
        self.client = Groq(api_key=api_key)
        self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.question_selector = None
    def generate(self, action, context):
        """
        Generate a question based on the action dict from DecisionEngine.
        Uses conversation history from context to avoid repeating questions.
        """
        action_type = action.get("type", "ask")

        # ── Closing ─────────────────────────────────────────────
        if action_type == "closing":
            return "Thank you for your time. This concludes the interview."

        # ── Intro / Greeting ────────────────────────────────────
        if action_type == "intro":
            return self._generate_intro(context)

        # ── Follow-up (weak answer) ─────────────────────────────
        if action_type == "followup":
            return self._generate_followup(action, context)

        # ── Behavioral Question ─────────────────────────────────
        topic = action.get("topic", "")
        if topic == "behavioral":
            return self._generate_behavioral(action, context)

        # ── Technical Question ──────────────────────────────────
        return self._generate_technical(action, context)

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

        prompt = INTRO_SYSTEM_PROMPT.format(
            skills=skills_str,
            experience=experience,
        )
        prompt += f"""

Session context:
- Candidate name: {name}
- Target role: {role_title}
- Profile source: {profile_source}
- If profile_source is resume, briefly reference their skills or experience.
- If profile_source is default, explain this is a structured {role_title} practice interview.
"""
        return self._call_llm(prompt)

    def _generate_technical(self, action, context):
        """Generate a technical question on a specific topic."""
        topic = action.get("topic", "general")
        domain = action.get("domain", topic)
        difficulty = action.get("difficulty", "medium")

        # Resume / question-bank path for domains that support personalization.
        if action.get("type") == "ask":
            selector = getattr(context, "question_selector", None) or self.question_selector
            if selector and domain in ("project_overview", "behavioral_ownership"):
                bank_question = selector.select_for_domain(
                    domain,
                    asked_questions=context.question_history,
                )
                if bank_question:
                    return _naturalize_static_question(domain, bank_question)

        # Deterministic Junior AI Engineer question bank.
        # Main domain questions are fixed so coverage stays balanced and defensible.
        if action.get("type") == "ask":
            domain_questions = {
                "project_overview": "Briefly explain one AI or machine learning project you worked on. What problem did it solve, what did you build, and what was the result?",
                "python": "In Python, how would you structure a small machine learning project so the code stays clean, reusable, and easy to debug?",
                "machine_learning": "How would you detect overfitting in a machine learning model, and what steps would you take to reduce it?",
                "data_preprocessing": "How would you handle missing values, categorical features, and scaling before training a machine learning model?",
                "model_evaluation": "For a classification model, how would you choose evaluation metrics such as accuracy, precision, recall, F1-score, and confusion matrix?",
                "nlp_speech_ai": "If you are building a speech or NLP-based AI system, what preprocessing steps would you apply before sending text to the model?",
                "apis_backend": "How would you expose a trained AI model through an API, and what request, response, and error-handling details would you include?",
                "deployment": "What steps would you take to deploy a small AI model and monitor its latency, errors, and performance after deployment?",
                "debugging_problem_solving": "If your AI pipeline gives poor results, how would you debug whether the issue is in the data, preprocessing, model, or evaluation?",
                "behavioral_ownership": "Tell me about a time you took ownership of a technical problem. What did you do, and what was the outcome?",
            }
            if domain in domain_questions:
                return _naturalize_static_question(domain, domain_questions[domain])

        system_prompt = TECHNICAL_SYSTEM_PROMPT.format(
            topic=topic,
            difficulty=difficulty,
        )

        system_prompt += f"""
        
Interview policy:
- You are interviewing for a {context.resume_data.get("role", "Junior AI Engineer")} role.
- Current required domain: {domain}.
- Ask exactly ONE focused question for this domain.
- Keep it practical and junior-level.
- Do not ask multiple questions at once.
- Do not keep drilling previous domains unless this is explicitly a follow-up.
- Avoid repeating previous questions.
- Prefer questions that reveal practical understanding, not textbook memorization.
"""

        # Build conversation context so LLM avoids repeating
        messages = self._build_history_text(context)
        if messages:
            full_prompt = (
                f"{system_prompt}\n\n"
                f"Previous questions asked in this interview:\n{messages}\n\n"
                f"Now ask a NEW question."
            )
        else:
            full_prompt = system_prompt

        return self._call_llm(full_prompt)

    def _generate_behavioral(self, action, context):
        """Generate a behavioral question, optionally targeting a category."""
        category = action.get("category", None)

        # Build conversation context so LLM avoids repeating
        messages = self._build_history_text(context)

        if category:
            full_prompt = (
                f"{BEHAVIORAL_SYSTEM_PROMPT}\n\n"
                f"Focus this question on the category: {category}\n\n"
            )
        else:
            full_prompt = f"{BEHAVIORAL_SYSTEM_PROMPT}\n\n"

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

        prompt += f"""
        
Follow-up policy:
- You are allowed only ONE follow-up for this domain.
- Current domain: {domain}.
- Ask one short, direct follow-up based on the candidate's weak answer.
- Do not start a long chain of follow-ups.
- Do not ask multiple questions at once.
"""
        return self._call_llm(prompt)

    # ════════════════════════════════════════════════════════════
    #  Helpers
    # ════════════════════════════════════════════════════════════

    def _build_history_text(self, context):
        """Build a text summary of previously asked questions."""
        if not context.question_history:
            return ""
        lines = []
        for i, q in enumerate(context.question_history, 1):
            lines.append(f"{i}. {q}")
        return "\n".join(lines)

    def _call_llm(self, prompt):
        """Make a single call to Groq with one retry on failure."""
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
                    max_tokens=180,
                )

                text = response.choices[0].message.content.strip()
                text = sanitize_interviewer_output(text)

                if text and len(text) > 5:
                    return text

                if attempt == 0:
                    print("[Groq LLM] Empty/short response on attempt 1, retrying...")
                    continue

                return text if text else "[Error generating question. Please try again.]"

            except Exception as e:
                if attempt == 0:
                    print(f"[Groq LLM] Attempt 1 failed: {e}, retrying...")
                    continue

                print(f"[Groq LLM Error] {e}")
                return "[Error generating question. Please try again.]"

        return "[Error generating question. Please try again.]"




def _naturalize_static_question(domain: str, question: str) -> str:
    """
    Lightly naturalize fixed blueprint questions without changing their intent.
    This is deterministic and safe for tests.
    """
    d = (domain or "").lower().strip()
    q = (question or "").strip()

    if not q:
        return q

    # Avoid changing already conversational follow-ups.
    if q.lower().startswith(("you mentioned", "can you walk me through", "let's", "suppose", "in a real")):
        return q

    rewrites = {
        "python": "Let's talk about Python project structure. In a small ML project, how would you organize the code so it stays clean, reusable, and easy to debug?",
        "machine_learning": "Let's move to overfitting. Suppose your training score is high but validation performance drops. How would you detect overfitting, and what would you do to reduce it?",
        "data_preprocessing": "Now let's talk about preprocessing. Before training a model, how would you handle missing values, categorical features, and scaling?",
        "model_evaluation": "For a classification model, how would you choose between accuracy, precision, recall, F1-score, and the confusion matrix?",
        "nlp_speech_ai": "Suppose you're building a speech or NLP-based AI system. What preprocessing would you apply before sending the text to the model?",
        "apis_backend": "Now imagine your model is trained and ready. How would you expose it through an API, including request, response, and error handling?",
        "deployment": "Let's move to deployment. How would you deploy a small AI model and monitor latency, errors, and model performance after release?",
        "debugging_problem_solving": "Suppose your AI pipeline starts giving poor results. How would you debug whether the issue is in the data, preprocessing, model, or evaluation?",
        "behavioral_ownership": "Tell me about a time you took ownership of a technical problem. What did you do, and what was the outcome?",
    }

    return rewrites.get(d, q)

