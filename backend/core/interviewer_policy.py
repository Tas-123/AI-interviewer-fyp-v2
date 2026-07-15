"""
Interviewer behavior contract — constants that define "interviewer mode".

The system asks, evaluates, and redirects. It does not coach, tutor, or answer
on behalf of the candidate.
"""

from __future__ import annotations

# Junior AI Engineer interview blueprint (domain coverage order).
INTERVIEW_BLUEPRINT: tuple[str, ...] = (
    "project_overview",
    "python",
    "machine_learning",
    "data_preprocessing",
    "model_evaluation",
    "nlp_speech_ai",
    "apis_backend",
    "deployment",
    "debugging_problem_solving",
    "behavioral_ownership",
)

# Turn limits
# Safety ceiling only — wrap-up still prefers full blueprint coverage first.
# Sized for intro + 10 domains + 1 probe each + skip/guard buffer.
MAX_TURNS_PER_DOMAIN: int = 1
MAX_PROBES_PER_DOMAIN: int = 1
MAX_TOTAL_INTERVIEW_TURNS: int = 28
MAX_CONTEXT_FOLLOWUPS_TOTAL: int = 3
# Explicit skip / change-topic budget per interview (soft "next question" does not count)
MAX_SKIPS_PER_INTERVIEW: int = 2

# Persona constraints enforced in prompts and post-processing
INTERVIEWER_PERSONA_RULES: tuple[str, ...] = (
    "Ask exactly one question per turn.",
    "Never provide the answer, hints, or step-by-step coaching.",
    "Never say phrases like 'Here's how you could answer' or 'For example, you might say'.",
    "Redirect off-topic answers back to the current question.",
    "Use a professional interviewer tone — not a friendly tutor.",
    "Probe weak answers with a focused follow-up; advance when sufficient.",
)

# Phrases that indicate assistant/coaching tone (used for sanitization checks)
COACHING_PHRASE_BLOCKLIST: tuple[str, ...] = (
    "here's how you could",
    "you might want to mention",
    "for example, you could say",
    "let me explain",
    "the correct answer is",
    "you should say",
    "tip:",
    "hint:",
)

# Spoken copy (single source for TTS closing paths)
INTERVIEW_CLOSING_SPOKEN = (
    "Thank you for your time. This concludes the interview. "
    "Your final report is now being generated."
)
INTERVIEW_CLOSING_TEXT = "Thank you for your time. This concludes the interview."
LLM_ERROR_TTS_FALLBACK = (
    "Welcome to the interview. Please briefly introduce yourself and tell me "
    "what kind of role or area you would like this interview to focus on."
)

# Default candidate profile when none is supplied (voice demo fallback).
DEFAULT_CANDIDATE_PROFILE: dict = {
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": [
        "Python",
        "Machine Learning",
        "Deep Learning",
        "NLP",
        "APIs",
        "Data Preprocessing",
        "Model Evaluation",
    ],
    "experience": (
        "Entry-level to junior AI engineer with project experience in Python, "
        "machine learning, deep learning, NLP, APIs, and AI applications."
    ),
}
