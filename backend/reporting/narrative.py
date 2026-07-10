"""LLM-generated executive and overall summaries with rule-based fallback."""

from __future__ import annotations

import json
import logging

from core.config import settings

logger = logging.getLogger(__name__)


def _rule_based_narrative(facts: dict) -> tuple[str, str]:
    report_type = facts.get("report_type", "incomplete")
    candidate = facts.get("candidate_name", "The candidate")
    role = facts.get("role_title", "Junior AI Engineer")
    overall = facts.get("overall_score", 0)
    signal = facts.get("hire_signal", "N/A")
    evaluated = facts.get("evaluated_turns", 0)
    coverage = facts.get("coverage_percent", 0)
    strengths = facts.get("strengths", [])[:2]
    improvements = facts.get("areas_for_improvement", [])[:2]

    if report_type == "aborted":
        executive = (
            f"No assessable interview data was captured for {candidate}. "
            "The session ended before any responses could be evaluated."
        )
        overall_summary = executive
        return executive, overall_summary

    strength_text = (
        f" Notable strengths included: {'; '.join(strengths)}." if strengths else ""
    )
    improve_text = (
        f" Key improvement areas: {'; '.join(improvements)}."
        if improvements
        else ""
    )

    executive = (
        f"{candidate} completed a {role} voice interview with {evaluated} evaluated "
        f"responses across {coverage:.0f}% of planned domains. "
        f"Overall performance was rated {overall:.1f}/5 with a recommendation signal "
        f"of {signal}.{strength_text}"
    )

    if report_type == "partial":
        executive += (
            " This is a preliminary report — the interview ended before full assessment."
        )

    overall_summary = (
        f"The interview covered technical and communication dimensions for the {role} role. "
        f"{candidate} demonstrated {_tone_from_score(overall)} overall performance "
        f"based on scored responses.{strength_text}{improve_text} "
        f"Recommendation signal: {signal}."
    )
    if report_type != "complete":
        overall_summary += (
            " Treat ratings as directional only until a full interview is completed."
        )

    return executive.strip(), overall_summary.strip()


def _tone_from_score(score: float) -> str:
    if score >= 4.0:
        return "strong"
    if score >= 3.0:
        return "solid"
    if score >= 2.0:
        return "mixed"
    return "limited"


def generate_narrative_summaries(
    facts: dict,
    *,
    llm_client=None,
    llm_model: str | None = None,
) -> tuple[str, str]:
    """Return (executive_summary, overall_summary)."""
    fallback = _rule_based_narrative(facts)
    if llm_client is None:
        try:
            from groq import Groq

            if not settings.groq_api_key:
                return fallback
            llm_client = Groq(api_key=settings.groq_api_key)
            llm_model = llm_model or settings.groq_model
        except Exception:
            return fallback

    prompt = f"""You are writing recruiter-facing interview summaries. Use ONLY the facts below.
Do not invent skills, scores, or events. Plain professional English.

FACTS (JSON):
{json.dumps(facts, indent=2)}

Return strict JSON:
{{
  "executive_summary": "3-5 sentences for a busy recruiter",
  "overall_summary": "One paragraph overview in simple language"
}}
"""
    try:
        response = llm_client.chat.completions.create(
            model=llm_model or settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": "You write concise, factual interview summaries. Output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        executive = str(parsed.get("executive_summary", "")).strip()
        overall = str(parsed.get("overall_summary", "")).strip()
        if executive and overall:
            return executive, overall
    except Exception as exc:
        logger.warning("LLM narrative generation failed, using fallback: %s", exc)

    return fallback
