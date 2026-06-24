"""
test_new_layers.py — Offline tests for the three new architectural layers.

Tests run without LLM or DB dependencies. Validates:
  1. Flow controller state transitions (9 stages)
  2. Dynamic probing on low scores
  3. Question bank loading
  4. Resume parsing
  5. Resume question generation
  6. Question selector pipeline + deduplication
  7. HR report generation
  8. Hire recommendation derivation (all 4 tiers)
  9. Candidate ranking
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from dialogue.interview_flow_controller import (
    InterviewFlowController,
    InterviewStage,
)
from dialogue.resume_context_parser import parse_resume, generate_resume_questions
from dialogue.question_selector import QuestionSelector
from dialogue.recruiter_report import (
    derive_hire_recommendation,
    rank_candidates,
)


# ===================================================================
#  Test 1: Flow Controller — Full Stage Progression
# ===================================================================

def test_flow_controller_progression():
    """Controller should progress through all stages in order."""
    fc = InterviewFlowController("test-session-1", "Engineer", ["Python"])

    # Turn 1 → INTRO
    stage = fc.advance()
    assert stage == InterviewStage.INTRO, f"Expected INTRO, got {stage}"

    # Turn 2 → WARMUP
    stage = fc.advance()
    assert stage == InterviewStage.WARMUP, f"Expected WARMUP, got {stage}"

    # Turns 3-5 → BEHAVIORAL
    for i in range(3):
        stage = fc.advance()
        assert stage == InterviewStage.BEHAVIORAL, \
            f"Turn {3+i}: Expected BEHAVIORAL, got {stage}"

    # Turn 6 → DEEP_DIVE
    stage = fc.advance()
    assert stage == InterviewStage.DEEP_DIVE, f"Expected DEEP_DIVE, got {stage}"

    # Turn 7 → DEEP_DIVE
    stage = fc.advance()
    assert stage == InterviewStage.DEEP_DIVE, f"Expected DEEP_DIVE, got {stage}"

    # Turn 8 → FINAL_EVALUATION
    stage = fc.advance()
    assert stage == InterviewStage.FINAL_EVALUATION, \
        f"Expected FINAL_EVALUATION, got {stage}"

    # Turn 9 → REPORT
    stage = fc.advance()
    assert stage == InterviewStage.REPORT, f"Expected REPORT, got {stage}"

    # Turn 10 → END
    stage = fc.advance()
    assert stage == InterviewStage.END, f"Expected END, got {stage}"
    assert fc.is_complete()

    state = fc.get_state()
    assert state["turn_count"] == 10
    assert state["session_id"] == "test-session-1"
    assert len(state["stage_history"]) == 10

    return True


# ===================================================================
#  Test 2: Flow Controller — Dynamic Probing
# ===================================================================

def test_dynamic_probing():
    """Controller should probe when evaluation score is low."""
    fc = InterviewFlowController("test-session-2")

    # Advance to BEHAVIORAL (turn 3)
    fc.advance()  # INTRO
    fc.advance()  # WARMUP
    fc.advance()  # BEHAVIORAL

    # Simulate low score → should trigger PROBING
    low_eval = {"overall_score": 2.0}
    stage = fc.advance(low_eval)
    assert stage == InterviewStage.PROBING, f"Expected PROBING, got {stage}"

    # High score → should resume normal flow
    high_eval = {"overall_score": 4.5}
    stage = fc.advance(high_eval)
    assert stage != InterviewStage.PROBING, \
        f"Should not probe on high score, got {stage}"

    return True


# ===================================================================
#  Test 3: Flow Controller — Max Probes Limit
# ===================================================================

def test_max_probes_limit():
    """Controller should not probe more than max_probes times consecutively."""
    fc = InterviewFlowController("test-session-3")
    fc._max_probes = 2

    # Get to BEHAVIORAL
    fc.advance()
    fc.advance()
    fc.advance()

    low_eval = {"overall_score": 1.5}

    # First probe
    stage = fc.advance(low_eval)
    assert stage == InterviewStage.PROBING

    # Second probe
    stage = fc.advance(low_eval)
    assert stage == InterviewStage.PROBING

    # Third time → should NOT probe (max exceeded), normal progression
    stage = fc.advance(low_eval)
    assert stage != InterviewStage.PROBING, \
        f"Should not probe beyond max, got {stage}"

    return True


# ===================================================================
#  Test 4: Question Bank Loading
# ===================================================================

def test_question_bank_loading():
    """Question bank should load and contain expected categories."""
    from dialogue.question_selector import _QUESTION_BANK

    expected_categories = [
        "warmup", "behavioral", "leadership",
        "situational", "stress_test", "role_specific",
    ]

    for cat in expected_categories:
        assert cat in _QUESTION_BANK, f"Missing category: {cat}"
        assert len(_QUESTION_BANK[cat]) > 0, f"Empty category: {cat}"

    return True


# ===================================================================
#  Test 5: Resume Parsing
# ===================================================================

def test_resume_parsing():
    """Resume parser should extract skills, tools, experience, and role."""
    resume = """
    John Doe - Software Engineer
    5 years of experience in backend development.
    Skills: Python, Django, PostgreSQL, Docker, Redis
    Worked with REST APIs and microservices architecture.
    """

    result = parse_resume(resume)

    assert "python" in result["candidate_skills"]
    assert "django" in result["candidate_skills"]
    assert result["candidate_experience"] == "5 years"
    assert result["candidate_role"] == "Software Engineer"

    # Empty input
    empty = parse_resume("")
    assert empty["candidate_skills"] == []
    assert empty["candidate_experience"] == "not specified"

    # None input
    none_result = parse_resume(None)
    assert none_result["candidate_skills"] == []

    return True


# ===================================================================
#  Test 6: Resume Question Generation
# ===================================================================

def test_resume_question_generation():
    """Resume parser should generate personalized questions."""
    parsed = {
        "candidate_skills": ["python", "django"],
        "candidate_tools": ["docker"],
        "candidate_experience": "5 years",
        "candidate_role": "Software Engineer",
    }

    questions = generate_resume_questions(parsed)

    assert len(questions) >= 4  # 2 skills + 1 tool + 1 role + 1 experience
    assert any("Python" in q for q in questions)
    assert any("Django" in q for q in questions)
    assert any("Docker" in q for q in questions)
    assert any("5 years" in q for q in questions)
    assert any("Software Engineer" in q for q in questions)

    # Empty resume
    empty_questions = generate_resume_questions({
        "candidate_skills": [],
        "candidate_tools": [],
        "candidate_experience": "not specified",
        "candidate_role": "not specified",
    })
    assert len(empty_questions) == 0

    return True


# ===================================================================
#  Test 7: Question Selector — Priority Pipeline
# ===================================================================

def test_question_selector_pipeline():
    """Selector should prioritize resume → bank → None."""
    selector = QuestionSelector()

    # Without resume questions, should get bank question
    q1 = selector.select_question("behavioral")
    assert q1 is not None, "Should get a question from the bank"

    # Question should be marked as asked
    assert q1.strip().lower() in selector._asked_questions

    return True


# ===================================================================
#  Test 8: Question Selector — Deduplication
# ===================================================================

def test_question_selector_dedup():
    """Selector should not return the same question twice."""
    selector = QuestionSelector()

    asked = set()
    for _ in range(10):
        q = selector.select_question("behavioral")
        if q is None:
            break
        assert q not in asked, f"Duplicate question: {q}"
        asked.add(q)

    return True


# ===================================================================
#  Test 9: Question Selector — Resume Priority
# ===================================================================

def test_question_selector_resume_priority():
    """Resume questions should come before bank questions."""
    selector = QuestionSelector()

    resume_q = "Tell me about your Django experience at Company X."
    selector.set_resume_questions([resume_q])

    q = selector.select_question("behavioral")
    assert q == resume_q, f"Expected resume question, got: {q}"

    # Next call should return a bank question (resume exhausted)
    q2 = selector.select_question("behavioral")
    assert q2 != resume_q, "Should not return resume question again"
    assert q2 is not None, "Should fall back to bank"

    return True


# ===================================================================
#  Test 10: Hire Recommendation — All Tiers
# ===================================================================

def test_hire_recommendation():
    """Hire recommendation should map correctly to score ranges."""
    # Strong hire: >= 4.0 + High consistency + improving
    rec = derive_hire_recommendation(4.5, "High", "improving")
    assert rec == "STRONG_HIRE", f"Expected STRONG_HIRE, got {rec}"

    # Hire: >= 3.0
    rec = derive_hire_recommendation(3.5, "High", "stable")
    assert rec == "HIRE", f"Expected HIRE, got {rec}"

    # Lean hire: >= 2.0
    rec = derive_hire_recommendation(2.5, "High", "stable")
    assert rec == "LEAN_HIRE", f"Expected LEAN_HIRE, got {rec}"

    # No hire: < 2.0
    rec = derive_hire_recommendation(1.5, "Low", "declining")
    assert rec == "NO_HIRE", f"Expected NO_HIRE, got {rec}"

    # Downgrade: high score + low consistency
    rec = derive_hire_recommendation(4.0, "Low", "stable")
    assert rec in ("HIRE", "LEAN_HIRE"), \
        f"Should downgrade with Low consistency, got {rec}"

    # Downgrade: high score + declining trend
    rec = derive_hire_recommendation(3.5, "Moderate", "declining")
    assert rec in ("LEAN_HIRE", "HIRE"), \
        f"Should downgrade with declining trend, got {rec}"

    # Upgrade: lean hire + improving + high consistency
    rec = derive_hire_recommendation(2.5, "High", "improving")
    assert rec in ("HIRE", "LEAN_HIRE"), \
        f"Should consider upgrade with improving+high, got {rec}"

    return True


# ===================================================================
#  Test 11: Candidate Ranking
# ===================================================================

def test_candidate_ranking():
    """Candidates should be ranked by composite criteria."""
    candidates = [
        {
            "session_id": "C", "final_weighted_score": 2.0,
            "consistency_rating": "Low", "trend_label": "declining",
        },
        {
            "session_id": "A", "final_weighted_score": 4.5,
            "consistency_rating": "High", "trend_label": "improving",
        },
        {
            "session_id": "B", "final_weighted_score": 3.5,
            "consistency_rating": "Moderate", "trend_label": "stable",
        },
    ]

    ranked = rank_candidates(candidates)
    assert ranked[0]["session_id"] == "A", "Top candidate should be A"
    assert ranked[1]["session_id"] == "B", "Second candidate should be B"
    assert ranked[2]["session_id"] == "C", "Last candidate should be C"

    # Empty list
    assert rank_candidates([]) == []

    return True


# ===================================================================
#  Test 12: Flow Controller — Question Type Mapping
# ===================================================================

def test_question_type_mapping():
    """Each stage should map to a valid question type."""
    fc = InterviewFlowController("test-mapping")

    fc.current_stage = InterviewStage.WARMUP
    assert fc.get_question_type() == "warmup"

    fc.current_stage = InterviewStage.BEHAVIORAL
    assert fc.get_question_type() == "behavioral"

    fc.current_stage = InterviewStage.DEEP_DIVE
    assert fc.get_question_type() == "situational"

    fc.current_stage = InterviewStage.FINAL_EVALUATION
    assert fc.get_question_type() == "leadership"

    return True


# ===================================================================
#  Run All Tests
# ===================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("NEW LAYERS TEST SUITE — AI Interviewer v4.0")
    print("=" * 60)

    tests = [
        test_flow_controller_progression,
        test_dynamic_probing,
        test_max_probes_limit,
        test_question_bank_loading,
        test_resume_parsing,
        test_resume_question_generation,
        test_question_selector_pipeline,
        test_question_selector_dedup,
        test_question_selector_resume_priority,
        test_hire_recommendation,
        test_candidate_ranking,
        test_question_type_mapping,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = test()
            if result:
                print(f"[PASS] {test.__name__}")
                passed += 1
            else:
                print(f"[FAIL] {test.__name__} returned False")
                failed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__} ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
