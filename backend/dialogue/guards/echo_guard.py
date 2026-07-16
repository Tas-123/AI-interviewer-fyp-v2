"""Echo guard — detects bot/question repetition in STT output."""

from __future__ import annotations

import re

from dialogue.guards.types import GuardContext, GuardResult


_REDIRECT_PREFIXES = (
    "let's stay on the current interview question.",
    "your last response did not clearly answer what i asked.",
    "please answer this directly:",
    "let's stay focused on the interview.",
    "please answer this question directly:",
    "please answer the current interview question directly:",
    "i'll rephrase the question.",
    "i'll ask it another way.",
    "sure, i'll repeat the question.",
    "no problem, i'll repeat it clearly.",
    "i may have captured an instruction or external prompt instead of your answer.",
    "i detected that the interviewer prompt may have been repeated instead of a candidate answer.",
    "please answer in your own words.",
    "please answer with your own experience.",
    "let's come back to this.",
    "we'll stay on the interview for now.",
    "one more pass on that question.",
    "happy to repeat that.",
    "happy to repeat.",
    "i'll say it again briefly.",
    "that's okay — let me ask it a simpler way.",
    "that's okay — let me ask it more simply.",
    "no problem. here's a small hint:",
    "let's stay with the current question for now.",
    "let's finish the current question first, then we can move on.",
    "we've already skipped a couple of areas.",
    "let's finish this one first.",
    "could you connect that to this question?",
    "let's focus on this.",
    "let's focus on the task at hand.",
    "let's focus on your hands-on experience with text preprocessing.",
    "sure — let's move on to a different area of the interview.",
    "alright —",
    "next up:",
    "shifting topics briefly —",
    "building on that —",
)


def _dedupe_repeated_question_clauses(q: str) -> str:
    """Collapse stacked copies of the same question sentence."""
    text = (q or "").strip()
    if not text or "?" not in text:
        return text

    # Split on sentence boundaries while keeping question marks attached.
    parts = [p.strip() for p in re.split(r"(?<=[?.!])\s+", text) if p.strip()]
    if len(parts) <= 1:
        return text

    seen_norm: set[str] = set()
    kept: list[str] = []
    for part in parts:
        # Normalize for comparison: lowercase, collapse spaces, drop trailing fillers.
        norm = re.sub(r"\s+", " ", part.lower()).strip(" .")
        norm = re.sub(
            r"\s*please answer with your own experience\.?\s*$",
            "",
            norm,
        ).strip()
        if not norm:
            continue
        if norm in seen_norm:
            continue
        # Near-duplicate: one clause contains another long question clause.
        if any(
            norm in prev or prev in norm
            for prev in seen_norm
            if "?" in prev and len(prev) > 20
        ):
            # Prefer the shorter cleaner form when one contains the other.
            continue
        seen_norm.add(norm)
        kept.append(part)

    if not kept:
        return text

    # Prefer the last remaining question clause if we still have extras.
    question_parts = [p for p in kept if "?" in p]
    if question_parts:
        # Keep at most one trailing "please answer..." style instruction.
        core = question_parts[-1]
        return core.strip()
    return " ".join(kept).strip()


def canonicalize_for_store(question: str = "") -> str:
    """Strip wrappers and collapse stacked duplicates into one clean question."""
    q = canonical_interview_question(question)
    q = _dedupe_repeated_question_clauses(q)
    for label in ("[Follow-up]", "[follow-up]", "Follow-up:", "follow-up:"):
        q = q.replace(label, "").strip()
    # Drop duplicated trailing experience instructions.
    q = re.sub(
        r"(?:\s*Please answer with your own experience\.?)+$",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    return q


def canonical_interview_question(last_question: str = "") -> str:
    """Strip stacked guard redirects so we never nest redirect text in TTS."""
    q = (last_question or "").strip()
    if not q:
        return ""

    changed = True
    safety = 0
    while changed and safety < 20:
        safety += 1
        changed = False
        lower = q.lower().strip()
        for prefix in _REDIRECT_PREFIXES:
            if lower.startswith(prefix):
                q = q[len(prefix) :].strip()
                changed = True
                break
        # Also strip leading soft openers repeatedly.
        m = re.match(
            r"^(alright —|next up:|shifting topics briefly —|building on that —)\s*",
            q,
            flags=re.IGNORECASE,
        )
        if m:
            q = q[m.end() :].strip()
            changed = True

    return _dedupe_repeated_question_clauses(q.strip())


def short_repeat_question(last_question: str = "", interview_context=None) -> str:
    """Repeat only the core interview question without long greeting text."""
    if interview_context is not None and hasattr(
        interview_context, "get_active_canonical_question"
    ):
        stored = interview_context.get_active_canonical_question(last_question)
        if stored:
            q = stored
        else:
            q = canonicalize_for_store(last_question)
    else:
        q = canonicalize_for_store(last_question)

    lq = q.lower()

    if not q:
        return "Please answer the current interview question in your own words."

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
        return (
            "Please introduce yourself and tell me about one AI or machine "
            "learning project you worked on."
        )

    for prefix in ("[Follow-up]", "[follow-up]", "Follow-up:", "follow-up:"):
        q = q.replace(prefix, "").strip()

    if len(q.split()) > 28 and "?" in q:
        parts = [p.strip() for p in q.split(".") if p.strip()]
        question_parts = [p for p in parts if "?" in p]
        if question_parts:
            q = question_parts[-1].strip()

    return q


def looks_like_bot_question_echo(transcript: str, last_question: str = "") -> bool:
    """Detect when STT captured the interviewer prompt instead of a candidate answer."""
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
        "standard scaling",
    ]
    question_like_markers = [
        "can you", "could you", "please", "tell me about",
        "how would you", "what steps would you", "walk me through",
        "let's talk about", "question is", "answer this question",
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
        "say this answer",
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

    if sum(1 for p in echo_phrases if p in t) >= 2:
        return True

    overlap = 0.0
    if q:

        def words(x: str) -> set[str]:
            return set(re.findall(r"[a-zA-Z]{4,}", x))

        tw = words(t)
        qw = words(q)
        if len(tw) >= 6 and len(qw) >= 6:
            overlap = len(tw & qw) / max(1, len(qw))

    if has_candidate_answer_marker:
        return overlap >= 0.85
    if is_question_like and overlap >= 0.85:
        return True
    return False


class EchoGuard:
    """Guard that blocks scoring when the transcript is an echo of the bot question."""

    name = "echo"

    def check(self, ctx: GuardContext) -> GuardResult:
        if not looks_like_bot_question_echo(ctx.transcript, ctx.last_question):
            return GuardResult(triggered=False)

        from dialogue.rephrase_policy import rephrase_recovery, resolve_core_question

        core = resolve_core_question(ctx.interview_context, ctx.last_question)
        response = rephrase_recovery(
            core_question=core,
            domain=getattr(ctx.interview_context, "current_domain", "")
            if ctx.interview_context
            else "",
            mode="repeat",
            llm_client=ctx.llm_client,
            llm_model=ctx.llm_model,
        )
        return GuardResult(
            triggered=True,
            decision_type="BOT_OR_EXTERNAL_PROMPT_ECHO",
            response_text=response,
            should_evaluate=False,
            metadata={"guard": self.name},
        )
