"""
Interview Context — Tracks all session state for one interview.
"""

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

        # Technical skills extracted from resume
        self.skills = [skill.lower() for skill in resume_data.get("skills", [])]

        # Junior AI Engineer interview blueprint.
        # This controls balanced domain coverage so the bot does not over-probe one topic.
        self.interview_blueprint = [
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
        ]

        self.domain_coverage = {domain: 0 for domain in self.interview_blueprint}
        self.domain_probe_counts = {domain: 0 for domain in self.interview_blueprint}
        self.current_domain = self.interview_blueprint[0]

        # Hard limits to prevent long, repetitive interviews.
        self.max_turns_per_domain = 1
        self.max_probes_per_domain = 1
        self.max_total_interview_turns = 12

        # Controlled adaptive context follow-ups.
        # Keeps the interview adaptive without becoming too long.
        self.max_context_followups_total = 3
        self.context_followups_used = 0
        self.context_followup_domains = set()

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

    def add_turn(self, question, transcript):
        """Record one Q&A exchange."""
        self.question_history.append(question)
        self.transcript_history.append(transcript)
        self.turn_count += 1

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
        if not domain:
            return False

        if self.context_followups_used >= self.max_context_followups_total:
            return False

        if domain in self.context_followup_domains:
            return False

        return True

    def mark_context_followup(self, domain: str):
        """Record that a context follow-up was used for this domain."""
        if not domain:
            return

        self.context_followups_used += 1
        self.context_followup_domains.add(domain)


    def get_next_domain(self):
        """Return the next interview blueprint domain that still needs coverage."""
        for domain in self.interview_blueprint:
            if self.domain_coverage.get(domain, 0) < self.max_turns_per_domain:
                return domain
        return None

    def mark_domain_covered(self, domain: str):
        """Increment coverage count for a domain."""
        if not domain:
            return
        if domain not in self.domain_coverage:
            self.domain_coverage[domain] = 0
        self.domain_coverage[domain] += 1
        self.current_domain = domain

    def mark_domain_probe(self, domain: str):
        """Increment probe count for a domain."""
        if not domain:
            return
        if domain not in self.domain_probe_counts:
            self.domain_probe_counts[domain] = 0
        self.domain_probe_counts[domain] += 1

    def can_probe_domain(self, domain: str) -> bool:
        """Return whether the current domain can still be probed."""
        if not domain:
            return False
        return self.domain_probe_counts.get(domain, 0) < self.max_probes_per_domain

    def get_domain_summary(self) -> dict:
        """Return blueprint domain coverage/probe summary for reporting."""
        return {
            "blueprint": list(self.interview_blueprint),
            "coverage": dict(self.domain_coverage),
            "probe_counts": dict(self.domain_probe_counts),
            "current_domain": self.current_domain,
            "max_turns_per_domain": self.max_turns_per_domain,
            "max_probes_per_domain": self.max_probes_per_domain,
            "max_total_interview_turns": self.max_total_interview_turns,
        }

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
