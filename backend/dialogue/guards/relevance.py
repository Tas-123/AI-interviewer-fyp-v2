"""LLM-based answer relevance — replaces keyword-only domain matching."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from dialogue.guards.echo_guard import canonical_interview_question

logger = logging.getLogger(__name__)

RELEVANCE_CONFIDENCE_THRESHOLD = 0.65


@dataclass(frozen=True)
class RelevanceResult:
    relevant: bool
    confidence: float
    reason: str = ""


def is_follow_up_question(question: str) -> bool:
    """True for PROBE / evaluator follow-ups that keyword rules cannot cover."""
    q = (question or "").strip().lower()
    if not q:
        return False
    for marker in (
        "[follow-up]",
        "[follow up]",
        "follow-up:",
        "follow up:",
        "that's useful context",
        "thanks — that helps",
        "thanks - that helps",
        "fair enough",
        "building on that",
        "interesting",
    ):
        if marker in q:
            return True
    return False


def semantic_answer_relevance(
    transcript: str,
    last_question: str,
    *,
    llm_client=None,
    llm_model: str = "",
) -> RelevanceResult:
    """
    Ask the LLM whether the candidate answer addresses the interview question.

    When uncertain or LLM unavailable, default to relevant (evaluate anyway).
    """
    answer = (transcript or "").strip()
    question = canonical_interview_question(last_question)

    if not answer or not question:
        return RelevanceResult(relevant=True, confidence=0.0, reason="empty_input")

    if len(answer.split()) < 4:
        return RelevanceResult(relevant=True, confidence=0.0, reason="short_answer")

    if is_follow_up_question(last_question):
        return RelevanceResult(relevant=True, confidence=0.0, reason="follow_up_question")

    if llm_client is None:
        return RelevanceResult(relevant=True, confidence=0.0, reason="no_llm_client")

    prompt = f"""
You are judging whether a job candidate's spoken answer addresses the interview question.

Return JSON only:
{{"relevant": true or false, "confidence": 0.0 to 1.0, "reason": "brief"}}

Rules:
- relevant=true if the answer attempts to address the question, even if incomplete or weak.
- relevant=false ONLY if the answer is clearly about a different topic or refuses to answer.
- Synonyms and natural phrasing count as relevant (e.g. "convolution layers" = "Conv2D").
- Do not require specific buzzwords.

Interview question:
{question}

Candidate answer:
{answer}
""".strip()

    try:
        response = llm_client.chat.completions.create(
            model=llm_model or "llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=80,
        )
        content = (response.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)
        data = json.loads(content)
        relevant = bool(data.get("relevant", True))
        confidence = float(data.get("confidence", 0.5))
        reason = str(data.get("reason", ""))
        return RelevanceResult(relevant=relevant, confidence=confidence, reason=reason)
    except Exception as exc:
        logger.warning("Semantic relevance check failed: %s", exc)
        return RelevanceResult(relevant=True, confidence=0.0, reason="llm_error")




def should_redirect_for_relevance(result: RelevanceResult) -> bool:
    """Redirect only when clearly irrelevant with sufficient confidence."""
    if result.relevant:
        return False
    return result.confidence >= RELEVANCE_CONFIDENCE_THRESHOLD


def generate_speakable_redirect(
    last_question: str,
    *,
    llm_client=None,
    llm_model: str = "",
    attempt: int = 1,
    interview_context=None,
) -> str:
    """Short, natural redirect — LLM when available, safe fallback otherwise."""
    from dialogue.rephrase_policy import rephrase_recovery, resolve_core_question

    if attempt >= 2:
        return "Thanks — let's move on to the next topic."

    core = resolve_core_question(interview_context, last_question)
    domain = ""
    if interview_context is not None:
        domain = str(getattr(interview_context, "current_domain", "") or "")
    return rephrase_recovery(
        core_question=core,
        domain=domain,
        mode="redirect",
        llm_client=llm_client,
        llm_model=llm_model,
    )
