"""Incomplete transcript guard — blocks scoring of partial STT fragments."""

from __future__ import annotations

from dialogue.guards.echo_guard import short_repeat_question
from dialogue.guards.types import GuardContext, GuardResult


def looks_like_incomplete_transcript(transcript: str, last_question: str = "") -> bool:
    """Detect partial STT fragments that should not be evaluated yet."""
    text = (transcript or "").strip()
    if not text:
        return True

    clean = text.strip(" .,!?'\"").lower()
    words = clean.split()
    word_count = len(words)

    if word_count <= 2:
        return True

    if word_count <= 4:
        technical_keywords = [
            "python", "model", "dataset", "accuracy", "precision", "recall",
            "missing", "categorical", "scaling", "api", "deploy", "overfitting",
        ]
        if any(k in clean for k in technical_keywords):
            return True

    if word_count <= 6:
        last_q = (last_question or "").lower()
        is_intro_question = any(
            m in last_q
            for m in [
                "introduce yourself",
                "project",
                "worked on",
                "tell me about",
                "machine learning project",
            ]
        )
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

    unfinished_endings = [
        "i would", "i will", "i used", "i use", "i was", "i have", "i had",
        "for missing", "for categorical", "for scaling", "the model", "the dataset",
        "my project", "in python", "because", "and then", "so", "like",
        "using", "with", "for", "to", "by",
    ]
    if clean in unfinished_endings:
        return True

    cut_words = {
        "and", "or", "but", "because", "with", "for", "to", "by",
        "using", "like", "then", "so", "when", "where", "which",
    }
    if words and words[-1] in cut_words:
        return True

    return False


def incomplete_transcript_response(transcript: str, last_question: str = "") -> str:
    """Ask candidate to continue without scoring partial fragments."""
    partial = (transcript or "").strip()
    if partial:
        return (
            f'I only caught part of your answer: "{partial}". '
            "Please continue your answer clearly and directly."
        )
    return "I could not capture your full answer. Please continue or repeat your answer."


class IncompleteGuard:
    """Guard that redirects when STT captured only a fragment of the answer."""

    name = "incomplete"

    def check(self, ctx: GuardContext) -> GuardResult:
        if not looks_like_incomplete_transcript(ctx.transcript, ctx.last_question):
            return GuardResult(triggered=False)

        words = (ctx.transcript or "").strip().split()
        interview_ctx = getattr(ctx, "interview_context", None)
        last_substantial = ""
        if interview_ctx is not None and hasattr(interview_ctx, "last_substantial_transcript"):
            last_substantial = interview_ctx.last_substantial_transcript(min_words=8)

        # Micro-fragments after a solid answer: do not quote junk like "Started."
        quote_source = (ctx.transcript or "").strip()
        if len(words) <= 3:
            quote_source = ""

        response = incomplete_transcript_response(quote_source, ctx.last_question)
        if last_substantial and len(words) <= 3:
            response = (
                "I still need your full answer on this question. "
                "Please continue clearly from where you left off."
            )

        return GuardResult(
            triggered=True,
            decision_type="INCOMPLETE_TRANSCRIPT_REDIRECT",
            response_text=response,
            should_evaluate=False,
            metadata={
                "guard": self.name,
                "question": ctx.last_question,
                "had_prior_substantial": bool(last_substantial),
            },
        )
