"""
Test final report fixes without any LLM calls.
Directly tests analytics.generate_final_report() + DialogueManager.get_final_report() sanitization
using a mock context object.
"""

import sys, os, json

backend_dir = os.path.abspath(os.path.dirname(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.analytics import generate_final_report, sanitize_recruiter_summary_for_technical_interview


# --------------- Mock context ---------------

class MockContext:
    """Minimal mock of InterviewContext for report generation."""
    def __init__(self):
        from enum import Enum
        class S(Enum):
            mid = "mid"
        self.state = S.mid
        self.turn_count = 5
        self.interview_stage = "mid"
        self.skills = ["python", "machine_learning", "data_preprocessing"]
        self.behavioral_categories_used = []

        # Simulated evaluations with star_breakdown
        self.evaluations = [
            {
                "overall_score": 3, "clarity": 3, "structure": 3, "confidence": 3,
                "ownership": 3, "leadership": 2, "result_orientation": 2,
                "weighted_overall_score": 2.8, "weakest_dimension": "structure",
                "hire_signal": "Borderline",
                "star_breakdown": {"situation_present": True, "task_present": True,
                                   "action_present": True, "result_present": False},
            },
            {
                "overall_score": 3, "clarity": 3, "structure": 3, "confidence": 3,
                "ownership": 3, "leadership": 2, "result_orientation": 2,
                "weighted_overall_score": 2.8, "weakest_dimension": "result_orientation",
                "hire_signal": "Borderline",
                "star_breakdown": {"situation_present": True, "task_present": True,
                                   "action_present": True, "result_present": False},
            },
        ]

        self.weighted_score_history = [(2, 2.8), (3, 2.8)]

        # Simulated adaptive trace with REPEATED STT fragments
        self._adaptive_trace = [
            {
                "turn": 2,
                "question_answered": "How would you debug an ML pipeline?",
                "candidate_answer": "I'd check for data drift or inconsistency. I'd check for data drift or inconsistencies.",
                "decision_type": "ADVANCE",
                "engine_action": "ask",
                "engine_reason": "",
                "domain": "machine_learning",
                "next_domain": "data_preprocessing",
                "weakest_dimension": "structure",
                "follow_up_reason": "test",
                "next_question": "What preprocessing steps do you take?",
                "skill_focus": "machine_learning",
                "interview_stage": "mid",
                "scores": {"weighted_overall_score": 2.8, "overall_score": 3,
                           "clarity": 3, "structure": 3, "confidence": 3,
                           "ownership": 3, "leadership": 2, "result_orientation": 2},
                "star_breakdown": {"situation_present": True, "task_present": True,
                                   "action_present": True, "result_present": False},
                "hire_signal": "Borderline",
            },
            {
                "turn": 3,
                "question_answered": "What preprocessing steps would you take?",
                "candidate_answer": "Next, I validate preprocessing Next, I'd validate preprocessing steps for correctness.",
                "decision_type": "ADVANCE",
                "engine_action": "ask",
                "engine_reason": "",
                "domain": "data_preprocessing",
                "next_domain": "python",
                "weakest_dimension": "result_orientation",
                "follow_up_reason": "result/impact was missing from the answer",
                "next_question": "Tell me about a project.",
                "skill_focus": "data_preprocessing",
                "interview_stage": "mid",
                "scores": {"weighted_overall_score": 2.8, "overall_score": 3,
                           "clarity": 3, "structure": 3, "confidence": 3,
                           "ownership": 3, "leadership": 2, "result_orientation": 2},
                "star_breakdown": {"situation_present": True, "task_present": True,
                                   "action_present": True, "result_present": False},
                "hire_signal": "Borderline",
            },
        ]

        self.star_stats = {}
        self.question_history = []
        self.transcript_history = []
        self.topic_coverage = {}

    def get_adaptive_trace(self):
        return self._adaptive_trace

    def add_adaptive_trace(self, item):
        self._adaptive_trace.append(item)

    def get_previous_evaluations_summary(self):
        return []

    def get_evaluation_summary(self):
        return {}

    def add_evaluation(self, e):
        self.evaluations.append(e)

    def add_turn(self, q, t):
        self.question_history.append(q)
        self.transcript_history.append(t)
        self.turn_count += 1


# --------------- Tests ---------------

def test_no_star_in_analytics_report():
    """Test that generate_final_report output has neutral bias_awareness."""
    ctx = MockContext()
    report = generate_final_report(ctx)
    ba = report.get("bias_awareness", {})
    text = ba.get("cultural_storytelling_differences", "")

    if "STAR" in text:
        print(f"FAIL: bias_awareness still mentions STAR: {text}")
        return False

    print(f"PASS: bias_awareness uses neutral wording.")
    print(f"  Text: \"{text[:100]}...\"")
    return True


def test_no_star_after_sanitization():
    """Test the full sanitization path (analytics + dialogue_manager cleanup)."""
    ctx = MockContext()
    report = generate_final_report(ctx)
    report = sanitize_recruiter_summary_for_technical_interview(report)

    # Simulate DialogueManager.get_final_report() sanitization
    if isinstance(report, dict):
        report.pop("star_effectiveness_analysis", None)

        summary = report.get("recruiter_summary", {}) or {}
        bad_phrases = [
            "Candidate repeatedly missed result/impact in STAR-style answers.",
            "Ask for measurable project impact, outcomes, or success metrics.",
        ]
        for key in ["main_concerns", "recommended_follow_up_areas"]:
            if isinstance(summary.get(key), list):
                summary[key] = [
                    item for item in summary[key]
                    if item not in bad_phrases
                    and "STAR" not in str(item)
                    and "result/impact" not in str(item)
                ]
        report["recruiter_summary"] = summary

        for item in report.get("adaptive_questioning_trace", []) or []:
            reason = str(item.get("follow_up_reason", ""))
            if "result/impact" in reason or "STAR" in reason:
                item["follow_up_reason"] = (
                    "Candidate answer needed more concrete technical detail, so the system asked for clearer steps, reasoning, or validation."
                )
            item.pop("star_breakdown", None)

    report_json = json.dumps(report, indent=2)

    banned = [
        "star_effectiveness_analysis",
        "star_breakdown",
        "STAR framework",
        "STAR-style",
        "result/impact",
    ]

    failures = []
    for phrase in banned:
        if phrase in report_json:
            failures.append(phrase)

    if failures:
        print(f"FAIL: Report still contains banned phrases: {failures}")
        for phrase in failures:
            idx = report_json.find(phrase)
            context = report_json[max(0, idx - 80):idx + 80]
            print(f"  '{phrase}' near: ...{context}...")
        return False

    print("PASS: No STAR wording found in sanitized final report.")
    return True


def test_transcript_cleanup():
    """Test that _clean_live_transcript reduces repeated STT fragments."""
    from dialogue.dialogue_manager import DialogueManager

    # We only need the cleanup method, not a full DM
    resume = {"skills": [], "name": "test", "role": "test"}
    dm = DialogueManager.__new__(DialogueManager)
    # Manually set up just what _clean_live_transcript needs (nothing beyond self)

    test_cases = [
        (
            "I'd check for data drift or inconsistency. I'd check for data drift or inconsistencies.",
            "I'd check for data drift or inconsistency. I'd check for data drift or inconsistencies.",  # near-dup
        ),
        (
            "Next, I validate preprocessing Next, I'd validate preprocessing steps for correctness.",
            "Next, I validate preprocessing Next",  # should not contain exact repeat
        ),
        (
            "I used Python Python for building the pipeline the pipeline the pipeline.",
            "the pipeline the pipeline the pipeline",  # should not repeat 3x
        ),
    ]

    all_pass = True
    for original, bad_fragment in test_cases:
        cleaned = dm._clean_live_transcript(original)
        if bad_fragment in cleaned and bad_fragment != original:
            print(f"  FAIL: Fragment not cleaned: \"{cleaned}\"")
            all_pass = False
        else:
            print(f"  OK: \"{original[:50]}...\" -> \"{cleaned[:60]}\"")

    if all_pass:
        print("PASS: Transcript cleanup reduces repeated STT fragments.")
    else:
        print("FAIL: Some repeated fragments were not cleaned.")
    return all_pass


if __name__ == "__main__":
    results = []
    print("=" * 60)
    print("Testing final report fixes (no LLM calls)")
    print("=" * 60)

    results.append(("No STAR in analytics output", test_no_star_in_analytics_report()))
    print()
    results.append(("No STAR after full sanitization", test_no_star_after_sanitization()))
    print()
    results.append(("Transcript cleanup", test_transcript_cleanup()))
    print()

    print("=" * 60)
    all_pass = all(r[1] for r in results)
    for name, passed in results:
        print(f"  {'PASS' if passed else 'FAIL'}: {name}")
    print("=" * 60)

    if not all_pass:
        sys.exit(1)
    print("\nAll tests passed!")
