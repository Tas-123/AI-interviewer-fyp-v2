"""Classify interview completion tier from evaluated turns and domain coverage."""

from __future__ import annotations

from dataclasses import dataclass

from dialogue.states import InterviewState
from reporting.schema import REPORT_TYPES


@dataclass(frozen=True)
class CompletionThresholds:
    complete_min_turns: int = 5
    # Full Junior AI Engineer interviews must visit the whole blueprint.
    complete_min_coverage_percent: float = 100.0
    partial_min_turns: int = 3
    partial_min_coverage_percent: float = 30.0


DEFAULT_THRESHOLDS = CompletionThresholds()


def count_evaluated_turns(context) -> int:
    """Scored turns — includes degraded floor scores; excludes pure error zeros."""
    count = 0
    for evaluation in getattr(context, "evaluations", []) or []:
        score = evaluation.get("overall_score", 0) or 0
        if score <= 0:
            continue
        if evaluation.get("is_error") and not evaluation.get("evaluation_degraded"):
            continue
        count += 1
    return count


def classify_report_type(
    context,
    coverage_percent: float,
    *,
    thresholds: CompletionThresholds = DEFAULT_THRESHOLDS,
) -> str:
    """
    Return one of: complete | partial | incomplete | aborted.

    Priority:
      1. aborted — zero evaluated turns
      2. complete — wrap-up + enough turns + coverage
      3. partial — enough turns + coverage (any termination)
      4. incomplete — everything else
    """
    evaluated = count_evaluated_turns(context)
    if evaluated == 0:
        return "aborted"

    is_wrapup = getattr(context, "state", None) == InterviewState.WRAPUP

    if (
        is_wrapup
        and evaluated >= thresholds.complete_min_turns
        and coverage_percent >= thresholds.complete_min_coverage_percent
    ):
        return "complete"

    if (
        evaluated >= thresholds.partial_min_turns
        and coverage_percent >= thresholds.partial_min_coverage_percent
    ):
        return "partial"

    return "incomplete"


def infer_termination_reason(context, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if getattr(context, "state", None) == InterviewState.WRAPUP:
        return "natural_completion"
    return "user_disconnect"


def completion_note_for_type(report_type: str) -> str:
    notes = {
        "complete": "Interview reached wrap-up with full blueprint domain coverage.",
        "partial": (
            "Interview ended with preliminary assessed data. Ratings are not final."
        ),
        "incomplete": (
            "Interview ended before sufficient assessment. Use this report for traceability only."
        ),
        "aborted": "No evaluated turns — session produced no assessable interview data.",
    }
    return notes.get(report_type, "Interview status unknown.")
