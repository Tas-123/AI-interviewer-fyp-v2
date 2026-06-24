"""
Interruption Manager — Handles AI barge-in and off-topic context guarding.

Two behaviors:
    1. BARGE-IN: Detects when a candidate is rambling (word count threshold)
    2. CONTEXT GUARD: Detects off-topic answers via keyword overlap similarity

Uses deterministic keyword analysis — no ML dependencies or embeddings.
Designed to be upgraded with embedding-based similarity later.
"""

import re
from collections import Counter


# ── Configuration ────────────────────────────────────────────────
BARGE_IN_WORD_THRESHOLD = 150       # words before AI interrupts
CONTEXT_SIMILARITY_THRESHOLD = 0.08  # minimum keyword overlap ratio
MIN_ANSWER_WORDS_FOR_CHECK = 8      # don't check very short answers

# Stop words to exclude from keyword extraction
STOP_WORDS = frozenset({
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "the", "a", "an", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "can", "may", "might",
    "shall", "must", "to", "of", "in", "for", "on", "with", "at",
    "by", "from", "as", "into", "about", "that", "this", "these",
    "those", "and", "but", "or", "so", "if", "then", "than",
    "not", "no", "very", "just", "also", "too", "some", "any",
    "all", "each", "every", "most", "more", "much", "many",
    "what", "when", "where", "how", "why", "which", "who",
    "tell", "describe", "explain", "give", "example", "time",
    "about", "please", "think", "know", "like", "well", "really",
    "thing", "things", "lot", "way", "make", "made", "get", "got",
    "go", "going", "went", "come", "came", "take", "took",
    "see", "saw", "look", "use", "used", "work", "worked",
})

# Barge-in messages
BARGE_IN_MESSAGES = [
    "Let's focus on the specific situation you handled.",
    "Could you summarize the key outcome of that experience?",
    "I appreciate the detail. Let's focus on the main result.",
]

# Context guard messages
CONTEXT_GUARD_MESSAGES = [
    "Let's return to the question I asked about.",
    "That's interesting, but could you address the original question?",
    "I'd like to hear your answer related to what I asked.",
]


class InterruptionManager:
    """
    Monitors candidate speech for interruption-worthy conditions.

    Provides two detection mechanisms:
    - Barge-in: response is too long / rambling
    - Context guard: response is off-topic relative to the question
    """

    def __init__(
        self,
        barge_in_threshold: int = BARGE_IN_WORD_THRESHOLD,
        similarity_threshold: float = CONTEXT_SIMILARITY_THRESHOLD,
    ):
        self.barge_in_threshold = barge_in_threshold
        self.similarity_threshold = similarity_threshold
        self._barge_in_index = 0
        self._guard_index = 0

    def check_barge_in(self, transcript: str) -> dict | None:
        """
        Check if the candidate's speech is too long and needs interruption.

        Args:
            transcript: accumulated speech text so far

        Returns:
            Interruption dict if barge-in needed, None otherwise.
        """
        word_count = len(transcript.split())
        if word_count > self.barge_in_threshold:
            msg = BARGE_IN_MESSAGES[self._barge_in_index % len(BARGE_IN_MESSAGES)]
            self._barge_in_index += 1
            return {
                "type": "interruption",
                "reason": "barge_in",
                "message": msg,
                "word_count": word_count,
            }
        return None

    def check_context_guard(
        self, question: str, answer: str
    ) -> dict | None:
        """
        Check if the candidate's answer is off-topic relative to the question.

        Uses keyword overlap similarity (Jaccard-like) between question
        and answer content words.

        Args:
            question: the AI's most recent question
            answer: the candidate's full answer

        Returns:
            Interruption dict if off-topic, None otherwise.
        """
        answer_words = len(answer.split())
        if answer_words < MIN_ANSWER_WORDS_FOR_CHECK:
            return None  # too short to judge

        q_keywords = _extract_keywords(question)
        a_keywords = _extract_keywords(answer)

        if not q_keywords or not a_keywords:
            return None

        # Compute keyword overlap ratio
        overlap = q_keywords & a_keywords
        union = q_keywords | a_keywords
        similarity = len(overlap) / len(union) if union else 0

        if similarity < self.similarity_threshold:
            msg = CONTEXT_GUARD_MESSAGES[
                self._guard_index % len(CONTEXT_GUARD_MESSAGES)
            ]
            self._guard_index += 1
            return {
                "type": "interruption",
                "reason": "off_topic",
                "message": msg,
                "similarity": round(similarity, 3),
            }
        return None

    def check_all(
        self, question: str, transcript: str
    ) -> dict | None:
        """
        Run all interruption checks.

        Returns the first triggered interruption, or None.
        """
        # Barge-in takes priority
        result = self.check_barge_in(transcript)
        if result:
            return result

        # Context guard
        result = self.check_context_guard(question, transcript)
        if result:
            return result

        return None


# ── Helpers ──────────────────────────────────────────────────────

def _extract_keywords(text: str) -> set:
    """Extract content keywords from text, excluding stop words."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}
