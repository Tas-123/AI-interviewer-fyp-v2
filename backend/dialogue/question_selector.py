"""
Question Selector — Multi-source question pipeline with deduplication.

Priority order:
    1. Resume-conditioned questions
    2. Question bank (category-matched)
    3. Returns None → caller falls back to LLM generation

Tracks all previously asked questions to prevent duplicates.
"""

import json
import os
import random


# Load question bank at module level
_QUESTION_BANK = {}
_bank_path = os.path.join(os.path.dirname(__file__), "question_bank.json")
try:
    with open(_bank_path, "r", encoding="utf-8") as f:
        _QUESTION_BANK = json.load(f)
except Exception as e:
    print(f"[QuestionSelector] Failed to load question bank: {e}")


# Mapping from interview stage question types to bank categories
STAGE_TO_CATEGORIES = {
    "warmup": ["warmup"],
    "behavioral": ["behavioral", "situational"],
    "situational": ["situational", "stress_test"],
    "leadership": ["leadership"],
    "stress_test": ["stress_test"],
    "role_specific": ["role_specific"],
}

# Mapping from blueprint domain to question bank category
DOMAIN_TO_QUESTION_TYPE = {
    "project_overview": "role_specific",
    "behavioral_ownership": "behavioral",
}


class QuestionSelector:
    """
    Selects interview questions from multiple sources with deduplication.

    Maintains a set of already-asked questions (normalized to lowercase)
    and ensures no question is repeated across sources.
    """

    def __init__(self):
        self._asked_questions: set = set()
        self._resume_questions: list = []
        self._resume_question_index = 0

    def set_resume_questions(self, questions: list):
        """
        Load resume-conditioned questions for this session.

        Args:
            questions: list of question strings generated from resume
        """
        self._resume_questions = questions or []
        self._resume_question_index = 0

    def select_for_domain(
        self,
        domain: str,
        asked_questions: list | None = None,
    ) -> str | None:
        """Select a question for a blueprint domain (resume-first, then bank)."""
        question_type = DOMAIN_TO_QUESTION_TYPE.get(domain, "role_specific")
        return self.select_question(question_type, asked_questions)

    def select_question(
        self,
        question_type: str,
        asked_questions: list | None = None,
    ) -> str | None:
        """
        Select a question using the priority pipeline.

        Args:
            question_type: category key (warmup, behavioral, etc.)
            asked_questions: optional external list of already-asked questions

        Returns:
            A question string, or None if no bank/resume questions available
            (caller should fall back to LLM generation).
        """
        # Merge external asked questions into our tracking set
        if asked_questions:
            for q in asked_questions:
                self._asked_questions.add(q.strip().lower())

        # ── Priority 1: Resume-conditioned questions ─────────────
        question = self._try_resume_question()
        if question:
            return question

        # ── Priority 2: Question bank ────────────────────────────
        question = self._try_bank_question(question_type)
        if question:
            return question

        # ── Priority 3: No match → return None (LLM fallback) ───
        return None

    def mark_asked(self, question: str):
        """Record a question as asked (for deduplication)."""
        if question:
            self._asked_questions.add(question.strip().lower())

    def get_asked_count(self) -> int:
        """Return the number of unique questions tracked."""
        return len(self._asked_questions)

    # ──────────────────────────────────────────────────────────────
    #  Private helpers
    # ──────────────────────────────────────────────────────────────

    def _try_resume_question(self) -> str | None:
        """Try to get the next unused resume-conditioned question."""
        while self._resume_question_index < len(self._resume_questions):
            q = self._resume_questions[self._resume_question_index]
            self._resume_question_index += 1
            if q.strip().lower() not in self._asked_questions:
                self._asked_questions.add(q.strip().lower())
                return q
        return None

    def _try_bank_question(self, question_type: str) -> str | None:
        """Try to get an unused question from the bank for the given type."""
        categories = STAGE_TO_CATEGORIES.get(question_type, [question_type])

        # Collect all candidate questions from matching categories
        candidates = []
        for cat in categories:
            candidates.extend(_QUESTION_BANK.get(cat, []))

        # Shuffle to avoid predictable ordering
        random.shuffle(candidates)

        for q in candidates:
            if q.strip().lower() not in self._asked_questions:
                self._asked_questions.add(q.strip().lower())
                return q

        return None
