"""
Interview Context — Tracks all session state for one interview.
"""

from core.role_registry import get_role_config
from dialogue.coverage_engine import CoverageEngine
from dialogue.states import InterviewState


# All behavioral categories the interviewer can draw from
BEHAVIORAL_CATEGORIES = [
    "conflict handling",
    "leadership experience",
    "failure example",
    "difficult decision",
    "team collaboration",
    "handling pressure",
    "taking initiative",
    "career motivation",
    "strengths and weaknesses",
]


class InterviewContext:
    def __init__(self, resume_data):
        self.state = InterviewState.INTRO
        self.resume_data = resume_data
        self.question_history = []
        self.transcript_history = []
        self.turn_count = 0

        # Session metadata (Phase 3 bootstrap)
        self.target_role = resume_data.get("target_role", "junior_ai_engineer")
        self.profile_source = resume_data.get("profile_source", "default")

        # Technical skills extracted from resume / default profile
        self.skills = [skill.lower() for skill in resume_data.get("skills", [])]

        # Blueprint coverage via CoverageEngine (role-driven structure)
        role_cfg = get_role_config(self.target_role)
        self.coverage = CoverageEngine(role_cfg)
        self.interview_blueprint = self.coverage.interview_blueprint
        self.domain_coverage = self.coverage.domain_coverage
        self.domain_probe_counts = self.coverage.domain_probe_counts
        self.current_domain = self.coverage.current_domain
        self.max_turns_per_domain = self.coverage.max_turns_per_domain
        self.max_probes_per_domain = self.coverage.max_probes_per_domain
        self.max_total_interview_turns = self.coverage.max_total_interview_turns
        self.max_context_followups_total = self.coverage.max_context_followups_total
        self.max_skips_per_interview = self.coverage.max_skips_per_interview
        self.context_followups_used = self.coverage.context_followups_used
        self.skips_used = 0
        self.context_followup_domains = self.coverage.context_followup_domains

        # Resume-conditioned question pipeline (optional)
        self.question_selector = None

        # Legacy compatibility
        self.topic_coverage = {skill: 0 for skill in self.skills}
        self.topic_coverage["behavioral"] = 0

        # Behavioral category tracking — avoid repeating categories
        self.behavioral_categories_available = list(BEHAVIORAL_CATEGORIES)
        self.behavioral_categories_used = []

        # Per-turn evaluations -- stores evaluation dicts from Evaluator
        self.evaluations = []

        # Weighted score history: list of (turn_number, weighted_score) tuples
        self.weighted_score_history = []

        # Cumulative STAR framework statistics
        self.star_stats = {
            "missing_result_count": 0,
            "weak_action_count": 0,
            "incomplete_star_count": 0,
        }

        # Stores per-turn reasoning trace for adaptive/contextual questioning.
        # This is used in the final report to prove why each follow-up was asked.
        self.adaptive_trace = []

        # Phase 6A: per-domain IDK attempts (rephrase → hint → skip)
        self.domain_idk_counts: dict[str, int] = {}

        # Phase 6C: domain assessment tracking for reporting
        self.assessed_domains: set[str] = set()
        self.skipped_domains: set[str] = set()

        # Guard redirect counter per canonical question (stops infinite loops)
        self.guard_redirect_counts: dict[str, int] = {}

    def add_turn(self, question, transcript):
        """Record one Q&A exchange."""
        self.question_history.append(question)
        self.transcript_history.append(transcript)
        self.turn_count += 1

    def get_recent_qa_pairs(self, n: int = 3) -> list[tuple[str, str]]:
        """Return up to n recent (question, answer) pairs for prompt continuity.

        Histories are recorded as (next_question, current_answer) per turn, so
        answer[i] generally responds to question[i-1]. The in-flight answer
        (before add_turn) is read from latest_answer_for_decision when present.
        """
        if n <= 0:
            return []

        questions = list(getattr(self, "question_history", None) or [])
        answers = list(getattr(self, "transcript_history", None) or [])
        pairs: list[tuple[str, str]] = []

        for i in range(1, len(answers)):
            answer = str(answers[i] or "").strip()
            if not answer:
                continue
            question = (
                str(questions[i - 1] or "").strip() if i - 1 < len(questions) else ""
            )
            if question:
                pairs.append((question, answer))

        pending = str(getattr(self, "latest_answer_for_decision", "") or "").strip()
        if pending and questions:
            last_q = str(questions[-1] or "").strip()
            if last_q and (not answers or str(answers[-1] or "").strip() != pending):
                pairs.append((last_q, pending))

        return pairs[-n:]

    def format_recent_qa_for_prompt(
        self,
        n: int = 3,
        *,
        max_chars: int = 1200,
    ) -> str:
        """Format recent Q&A pairs as a compact prompt block (soft char cap)."""
        pairs = self.get_recent_qa_pairs(n=n)
        if not pairs:
            return ""

        lines: list[str] = ["Relevant interview memory (recent Q&A):"]
        for question, answer in pairs:
            lines.append(f"Q: {question}")
            lines.append(f"A: {answer}")
            lines.append("")
        text = "\n".join(lines).strip()
        if max_chars > 0 and len(text) > max_chars:
            text = text[: max_chars - 3].rstrip() + "..."
        return text

    def add_evaluation(self, evaluation: dict):
        """Store an evaluation result and update tracking metrics."""
        self.evaluations.append(evaluation)

        # Track weighted score history
        weighted = evaluation.get("weighted_overall_score", 0)
        if weighted > 0:
            self.weighted_score_history.append(
                (self.turn_count, weighted)
            )

        # Update cumulative STAR stats
        star = evaluation.get("star_breakdown", {})
        if star:
            if not star.get("result_present", False):
                self.star_stats["missing_result_count"] += 1
            if not star.get("action_present", False):
                self.star_stats["weak_action_count"] += 1
            components = [star.get(k, False) for k in
                          ["situation_present", "task_present",
                           "action_present", "result_present"]]
            if not all(components):
                self.star_stats["incomplete_star_count"] += 1

    def add_adaptive_trace(self, trace_item: dict):
        """Store a single adaptive questioning trace item."""
        if not isinstance(trace_item, dict):
            return
        self.adaptive_trace.append(trace_item)

    def get_adaptive_trace(self) -> list:
        """Return adaptive questioning trace for reporting."""
        return list(self.adaptive_trace)

    def get_latest_evaluation(self):
        """Return the most recent evaluation, or None."""
        return self.evaluations[-1] if self.evaluations else None

    def get_evaluation_summary(self):
        """
        Aggregate all evaluations into a summary with averages.
        Returns None if no evaluations exist.
        Uses canonical short names as primary, with _score fallback.
        """
        scored = [e for e in self.evaluations if e.get("overall_score", 0) > 0]
        if not scored:
            return None

        # Canonical field names (short form) with _score fallbacks
        canonical_fields = [
            ("clarity", "clarity_score"),
            ("structure", "structure_score"),
            ("confidence", "confidence_score"),
            ("ownership", "ownership_score"),
            ("leadership", "leadership_score"),
            ("result_orientation", "result_score"),
        ]

        summary = {}
        for canon, legacy in canonical_fields:
            vals = [e.get(canon, e.get(legacy, 0)) for e in scored]
            valid_vals = [v for v in vals if v > 0]
            if valid_vals:
                summary[f"avg_{canon}"] = round(sum(valid_vals) / len(valid_vals), 2)

        # Overall score average
        overall_vals = [e.get("overall_score", 0) for e in scored]
        summary["avg_overall_score"] = round(sum(overall_vals) / len(overall_vals), 2)

        # Weighted overall average
        weighted_vals = [e.get("weighted_overall_score", 0)
                         for e in scored if e.get("weighted_overall_score", 0) > 0]
        if weighted_vals:
            summary["avg_weighted_overall_score"] = round(
                sum(weighted_vals) / len(weighted_vals), 2
            )

        # Determine overall hire signal from weighted average
        avg = summary.get("avg_weighted_overall_score",
                          summary.get("avg_overall_score", 0))
        if avg >= 4.0:
            summary["final_hire_signal"] = "Strong Hire"
        elif avg >= 3.0:
            summary["final_hire_signal"] = "Hire"
        elif avg >= 2.0:
            summary["final_hire_signal"] = "Borderline"
        else:
            summary["final_hire_signal"] = "No Hire"

        summary["total_evaluated"] = len(scored)
        summary["star_stats"] = dict(self.star_stats)
        return summary

    @property
    def interview_stage(self) -> str:
        """
        Derive the interview stage from turn count.
        EARLY  = turns 1–3
        MID    = turns 4–7
        LATE   = turns 8+
        """
        if self.turn_count <= 3:
            return "EARLY"
        elif self.turn_count <= 7:
            return "MID"
        else:
            return "LATE"

    def get_previous_evaluations_summary(self) -> list:
        """
        Return a compact list of previous evaluation summaries
        for the adaptive evaluation prompt.
        """
        summaries = []
        for i, ev in enumerate(self.evaluations):
            if ev.get("overall_score", 0) > 0:
                summaries.append({
                    "turn": i + 1,
                    "overall_score": ev.get("overall_score", 0),
                    "weakest_dimension": ev.get("weakest_dimension", "unknown"),
                    "hire_signal": ev.get("hire_signal", "N/A"),
                })
        return summaries


    def can_context_followup(self, domain: str) -> bool:
        """Allow limited answer-aware follow-ups across the whole interview."""
        return self.coverage.can_context_followup(domain)

    def mark_context_followup(self, domain: str):
        """Record that a context follow-up was used for this domain."""
        self.coverage.mark_context_followup(domain)
        self._sync_coverage_state()

    def get_next_domain(self):
        """Return the next interview blueprint domain that still needs coverage."""
        return self.coverage.get_next_domain()

    def mark_domain_covered(self, domain: str):
        """Increment coverage count for a domain."""
        self.coverage.mark_domain_covered(domain)
        self._sync_coverage_state()

    def set_current_domain(self, domain: str):
        """Set active blueprint domain on both context and coverage engine."""
        self.coverage.set_current_domain(domain)
        self._sync_coverage_state()

    def record_idk_attempt(self, domain: str) -> int:
        """Increment and return IDK attempt count for a domain."""
        key = (domain or "general").strip().lower()
        self.domain_idk_counts[key] = self.domain_idk_counts.get(key, 0) + 1
        return self.domain_idk_counts[key]

    def mark_domain_assessed(self, domain: str) -> None:
        if domain:
            self.assessed_domains.add(domain)

    def mark_domain_skipped(self, domain: str) -> None:
        if domain:
            self.skipped_domains.add(domain)

    def can_skip_domain(self) -> bool:
        return self.skips_used < getattr(self, "max_skips_per_interview", 2)

    def record_skip(self) -> int:
        """Increment skip budget usage; return new count."""
        self.skips_used = int(getattr(self, "skips_used", 0) or 0) + 1
        return self.skips_used

    def last_substantial_transcript(self, min_words: int = 8) -> str:
        """Most recent candidate utterance with enough content for evaluation."""
        for text in reversed(getattr(self, "transcript_history", []) or []):
            words = str(text or "").strip().split()
            if len(words) >= min_words:
                return str(text).strip()
        return ""

    def _canonical_active_question(self) -> str:
        from dialogue.guards.echo_guard import canonical_interview_question

        if not self.question_history:
            return ""
        return canonical_interview_question(self.question_history[-1])

    def get_domain_redirect_count(self) -> int:
        key = self._canonical_active_question()
        if not key:
            return 0
        return self.guard_redirect_counts.get(key, 0)

    def increment_domain_redirect(self) -> int:
        key = self._canonical_active_question()
        if not key:
            return 0
        self.guard_redirect_counts[key] = self.guard_redirect_counts.get(key, 0) + 1
        return self.guard_redirect_counts[key]

    def mark_domain_probe(self, domain: str):
        """Increment probe count for a domain."""
        self.coverage.mark_domain_probe(domain)
        self._sync_coverage_state()

    def can_probe_domain(self, domain: str) -> bool:
        """Return whether the current domain can still be probed."""
        return self.coverage.can_probe_domain(domain)

    def get_domain_summary(self) -> dict:
        """Return blueprint domain coverage/probe summary for reporting."""
        return self.coverage.get_summary()

    def _sync_coverage_state(self):
        """Keep legacy attribute aliases in sync with CoverageEngine."""
        self.domain_coverage = self.coverage.domain_coverage
        self.domain_probe_counts = self.coverage.domain_probe_counts
        self.current_domain = self.coverage.current_domain
        self.context_followups_used = self.coverage.context_followups_used
        self.context_followup_domains = self.coverage.context_followup_domains

    def get_next_behavioral_category(self):
        """
        Pop and return the next unused behavioral category.
        Returns None if all categories have been used.
        """
        if self.behavioral_categories_available:
            category = self.behavioral_categories_available.pop(0)
            self.behavioral_categories_used.append(category)
            return category
        return None
