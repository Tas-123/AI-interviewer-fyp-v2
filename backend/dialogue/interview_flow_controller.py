"""
Interview Flow Controller — State-driven interview lifecycle manager.

Manages a structured interview progression through 9 stages:
    INIT → INTRO → WARMUP → BEHAVIORAL → PROBING → DEEP_DIVE
    → FINAL_EVALUATION → REPORT → END

Integrates with the existing DialogueManager and InterviewContext
without modifying them. Reads evaluation data to make adaptive
stage transition decisions.
"""

from enum import Enum
from datetime import datetime


class InterviewStage(Enum):
    INIT = "init"
    INTRO = "intro"
    WARMUP = "warmup"
    BEHAVIORAL = "behavioral"
    PROBING = "probing"
    DEEP_DIVE = "deep_dive"
    FINAL_EVALUATION = "final_evaluation"
    REPORT = "report"
    END = "end"


# Maps interview stages to question categories for the question selector
STAGE_QUESTION_MAP = {
    InterviewStage.INTRO: "warmup",
    InterviewStage.WARMUP: "warmup",
    InterviewStage.BEHAVIORAL: "behavioral",
    InterviewStage.PROBING: "behavioral",
    InterviewStage.DEEP_DIVE: "situational",
    InterviewStage.FINAL_EVALUATION: "leadership",
}

# Score threshold below which the controller triggers probing
PROBE_THRESHOLD = 3.0


class InterviewFlowController:
    """
    Controls the structured interview lifecycle for a single session.

    Tracks interview progression, determines when to transition between
    stages, and decides whether to probe deeper based on candidate
    performance.
    """

    def __init__(self, session_id: str, candidate_role: str = "",
                 candidate_skills: list = None):
        self.session_id = session_id
        self.current_stage = InterviewStage.INIT
        self.turn_count = 0
        self.candidate_role = candidate_role
        self.candidate_skills = candidate_skills or []
        self.interview_start_time = datetime.utcnow().isoformat()
        self._probe_count = 0      # consecutive probes in current block
        self._max_probes = 2       # max consecutive probes before advancing
        self._stage_history = []   # track stage transitions

    # ──────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────

    def advance(self, last_evaluation: dict = None) -> InterviewStage:
        """
        Advance the interview to the next stage based on turn count
        and candidate performance.

        Args:
            last_evaluation: most recent evaluation dict (may be None)

        Returns:
            The new InterviewStage after transition.
        """
        self.turn_count += 1
        previous_stage = self.current_stage

        # Check if probing is warranted before normal progression
        if self._should_probe(last_evaluation):
            self.current_stage = InterviewStage.PROBING
            self._probe_count += 1
        else:
            self._probe_count = 0
            self.current_stage = self._next_stage_by_turn()

        self._stage_history.append({
            "turn": self.turn_count,
            "from": previous_stage.value,
            "to": self.current_stage.value,
        })
        return self.current_stage

    def get_question_type(self) -> str:
        """
        Map the current stage to a question category string.

        Returns:
            One of: warmup, behavioral, situational, leadership, stress_test
        """
        return STAGE_QUESTION_MAP.get(self.current_stage, "behavioral")

    def is_complete(self) -> bool:
        """Check if the interview has reached the END stage."""
        return self.current_stage == InterviewStage.END

    def get_state(self) -> dict:
        """Return a serializable snapshot of the controller state."""
        return {
            "session_id": self.session_id,
            "current_stage": self.current_stage.value,
            "turn_count": self.turn_count,
            "candidate_role": self.candidate_role,
            "candidate_skills": self.candidate_skills,
            "interview_start_time": self.interview_start_time,
            "stage_history": self._stage_history,
        }

    # ──────────────────────────────────────────────────────────────
    #  Private helpers
    # ──────────────────────────────────────────────────────────────

    def _next_stage_by_turn(self) -> InterviewStage:
        """Determine stage based on turn count (default progression)."""
        t = self.turn_count
        if t <= 1:
            return InterviewStage.INTRO
        elif t == 2:
            return InterviewStage.WARMUP
        elif t <= 5:
            return InterviewStage.BEHAVIORAL
        elif t == 6:
            return InterviewStage.DEEP_DIVE
        elif t == 7:
            return InterviewStage.DEEP_DIVE
        elif t == 8:
            return InterviewStage.FINAL_EVALUATION
        elif t == 9:
            return InterviewStage.REPORT
        else:
            return InterviewStage.END

    def _should_probe(self, evaluation: dict = None) -> bool:
        """
        Decide whether to enter PROBING instead of normal advancement.

        Conditions:
        - An evaluation exists with a score below the threshold
        - We haven't exceeded max consecutive probes
        - We're in a stage that supports probing (BEHAVIORAL or later)
        """
        if evaluation is None:
            return False
        if self._probe_count >= self._max_probes:
            return False

        # Only probe during active interview stages
        probeable_stages = {
            InterviewStage.BEHAVIORAL,
            InterviewStage.DEEP_DIVE,
            InterviewStage.PROBING,
        }
        if self.current_stage not in probeable_stages:
            return False

        overall = evaluation.get("overall_score", 5.0)
        return overall < PROBE_THRESHOLD
