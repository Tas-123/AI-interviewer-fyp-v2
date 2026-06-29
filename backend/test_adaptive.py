# test_adaptive.py -- Full Test Suite for AI Interviewer (v4.0)
"""
Tests the complete pipeline without requiring a live Gemini API key.
Validates:
  1-6: Original adaptive evaluation tests
  7-11: Intelligence layer upgrade tests
"""

import os
import sys

os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
sys.path.insert(0, os.path.dirname(__file__))

from dialogue.context import InterviewContext
from dialogue.decision_engine import DecisionEngine
from dialogue.states import InterviewState


# ===================================================================
#  Test 1: Interview Stage Property
# ===================================================================

def test_interview_stage():
    ctx = InterviewContext({"skills": ["Python"], "experience": "2 years"})
    assert ctx.interview_stage == "EARLY"
    for i in range(3):
        ctx.add_turn(f"Q{i+1}", f"A{i+1}")
    assert ctx.interview_stage == "EARLY"
    ctx.add_turn("Q4", "A4")
    assert ctx.interview_stage == "MID"
    for i in range(4):
        ctx.add_turn(f"Q{i+5}", f"A{i+5}")
    assert ctx.interview_stage == "LATE"
    print("[PASS] Test 1: interview_stage returns correct values")


# ===================================================================
#  Test 2: Adaptive Evaluation Validation
# ===================================================================

def test_validate_adaptive_evaluation():
    def validate_adaptive(data):
        score_fields = ["clarity", "structure", "confidence",
                        "ownership", "leadership", "result_orientation"]
        for field in score_fields:
            data[field] = max(1, min(5, int(data.get(field, 0))))
        scores = [data[f] for f in score_fields]
        data["overall_score"] = round(sum(scores) / len(scores), 2)
        min_idx = scores.index(min(scores))
        data["weakest_dimension"] = score_fields[min_idx]
        valid_signals = ["Strong Hire", "Hire", "Borderline", "No Hire"]
        if data.get("hire_signal") not in valid_signals:
            avg = data["overall_score"]
            if avg >= 4.0: data["hire_signal"] = "Strong Hire"
            elif avg >= 3.0: data["hire_signal"] = "Hire"
            elif avg >= 2.0: data["hire_signal"] = "Borderline"
            else: data["hire_signal"] = "No Hire"
        return data

    raw = {"clarity": 4, "structure": 2, "confidence": 3,
           "ownership": 5, "leadership": 1, "result_orientation": 3,
           "overall_score": 0, "weakest_dimension": "", "hire_signal": "invalid"}
    result = validate_adaptive(raw)
    assert result["weakest_dimension"] == "leadership"
    expected_avg = round((4+2+3+5+1+3) / 6, 2)
    assert result["overall_score"] == expected_avg
    assert result["hire_signal"] in ["Strong Hire", "Hire", "Borderline", "No Hire"]

    raw_extreme = {"clarity": 0, "structure": 7, "confidence": -1,
                   "ownership": 10, "leadership": 3, "result_orientation": 5}
    result2 = validate_adaptive(raw_extreme)
    for f in ["clarity","structure","confidence","ownership","leadership","result_orientation"]:
        assert 1 <= result2[f] <= 5, f"{f} not clamped: {result2[f]}"
    print("[PASS] Test 2: adaptive evaluation validation works correctly")


# ===================================================================
#  Test 3: Decision Validation
# ===================================================================

def test_validate_decision():
    def validate_decision(data):
        if data.get("type") not in ("PROBE", "ADVANCE"):
            data["type"] = "ADVANCE"
        if not data.get("next_question"):
            data["next_question"] = "Tell me about a challenging situation."
        return data

    valid = {"type": "PROBE", "next_question": "Tell me more about X"}
    result = validate_decision(valid)
    assert result["type"] == "PROBE"
    assert result["next_question"] == "Tell me more about X"

    invalid = {"type": "UNKNOWN", "next_question": ""}
    result2 = validate_decision(invalid)
    assert result2["type"] == "ADVANCE"
    assert len(result2["next_question"]) > 0
    print("[PASS] Test 3: decision validation works correctly")


# ===================================================================
#  Test 4: DecisionEngine.decide_from_adaptive
# ===================================================================

def test_decide_from_adaptive():
    engine = DecisionEngine()
    ctx = InterviewContext({"skills": ["Python"], "experience": "2 years"})
    ctx.state = InterviewState.BEHAVIORAL

    probe_result = {
        "evaluation": {"overall_score": 2.0},
        "decision": {"type": "PROBE", "next_question": "What specific results?"},
    }
    result = engine.decide_from_adaptive(probe_result, ctx)
    assert result["decision_type"] == "PROBE"
    assert ctx.state == InterviewState.BEHAVIORAL

    advance_result = {
        "evaluation": {"overall_score": 4.0},
        "decision": {"type": "ADVANCE", "next_question": "New question"},
    }
    ctx.topic_coverage["behavioral"] = 4
    result2 = engine.decide_from_adaptive(advance_result, ctx)
    assert result2["decision_type"] == "ADVANCE"
    assert ctx.state == InterviewState.WRAPUP
    print("[PASS] Test 4: decide_from_adaptive handles state transitions correctly")


# ===================================================================
#  Test 5: DecisionEngine.decide fallback return
# ===================================================================

def test_decide_fallback():
    engine = DecisionEngine()
    ctx = InterviewContext({"skills": [], "experience": "1 year"})
    ctx.state = InterviewState.WRAPUP
    result = engine.decide(ctx, "some answer")
    assert result is not None, "decide() returned None -- fallback missing!"
    assert result["type"] == "closing"
    print("[PASS] Test 5: decide() always returns a valid action")


# ===================================================================
#  Test 6: Previous Evaluations Summary
# ===================================================================

def test_previous_evaluations_summary():
    ctx = InterviewContext({"skills": ["Python"], "experience": "2 years"})
    ctx.add_evaluation({"overall_score": 3.5, "weakest_dimension": "structure", "hire_signal": "Hire"})
    ctx.add_evaluation({"overall_score": 0.0, "weakest_dimension": "unknown", "hire_signal": "N/A"})
    ctx.add_evaluation({"overall_score": 4.2, "weakest_dimension": "ownership", "hire_signal": "Strong Hire"})
    summary = ctx.get_previous_evaluations_summary()
    assert len(summary) == 2, f"Expected 2 valid summaries, got {len(summary)}"
    assert summary[0]["overall_score"] == 3.5
    assert summary[1]["weakest_dimension"] == "ownership"
    print("[PASS] Test 6: previous_evaluations_summary filters errors correctly")


# ===================================================================
#  Test 7: Weighted Scoring
# ===================================================================

def test_weighted_scoring():
    from dialogue.analytics import compute_weighted_score, DIMENSION_WEIGHTS

    scores = {"clarity": 4, "structure": 5, "confidence": 3,
              "ownership": 4, "leadership": 3, "result_orientation": 4}
    result = compute_weighted_score(scores)
    expected = round(5*0.25 + 4*0.20 + 4*0.20 + 3*0.15 + 4*0.10 + 3*0.10, 2)
    assert result == expected, f"Expected {expected}, got {result}"
    assert round(sum(DIMENSION_WEIGHTS.values()), 2) == 1.0
    print("[PASS] Test 7: weighted scoring computes correctly")


# ===================================================================
#  Test 8: STAR Tracking
# ===================================================================

def test_star_tracking():
    ctx = InterviewContext({"skills": ["Python"], "experience": "2 years"})

    # Complete STAR
    ctx.add_evaluation({
        "overall_score": 4.0, "weighted_overall_score": 4.0,
        "star_breakdown": {"situation_present": True, "task_present": True,
                           "action_present": True, "result_present": True},
    })
    assert ctx.star_stats["missing_result_count"] == 0
    assert ctx.star_stats["incomplete_star_count"] == 0

    # Missing result + action
    ctx.add_evaluation({
        "overall_score": 2.0, "weighted_overall_score": 2.0,
        "star_breakdown": {"situation_present": True, "task_present": True,
                           "action_present": False, "result_present": False},
    })
    assert ctx.star_stats["missing_result_count"] == 1
    assert ctx.star_stats["weak_action_count"] == 1
    assert ctx.star_stats["incomplete_star_count"] == 1
    print("[PASS] Test 8: STAR tracking counts correctly")


# ===================================================================
#  Test 9: Trend Detection
# ===================================================================

def test_trend_detection():
    from dialogue.analytics import detect_performance_trend

    improving = [(1, 2.0), (2, 2.5), (3, 2.2), (5, 3.5), (6, 3.8), (8, 4.2), (9, 4.5)]
    r1 = detect_performance_trend(improving)
    assert r1["performance_trend_label"] == "improving"

    declining = [(1, 4.5), (2, 4.2), (5, 3.0), (6, 2.8), (8, 2.0)]
    r2 = detect_performance_trend(declining)
    assert r2["performance_trend_label"] == "declining"

    stable = [(1, 3.0), (2, 3.1), (5, 3.0), (6, 3.2), (8, 3.1)]
    r3 = detect_performance_trend(stable)
    assert r3["performance_trend_label"] == "stable"
    print("[PASS] Test 9: trend detection labels correctly")


# ===================================================================
#  Test 10: Consistency Rating
# ===================================================================

def test_consistency_rating():
    from dialogue.analytics import compute_consistency_rating

    high = [(1, 3.0), (2, 3.1), (3, 2.9), (4, 3.0), (5, 3.1)]
    r1 = compute_consistency_rating(high)
    assert r1["consistency_rating"] == "High", f"Got {r1}"

    low = [(1, 1.0), (2, 5.0), (3, 1.5), (4, 4.5), (5, 2.0)]
    r2 = compute_consistency_rating(low)
    assert r2["consistency_rating"] == "Low", f"Got {r2}"

    single = [(1, 3.0)]
    r3 = compute_consistency_rating(single)
    assert r3["consistency_rating"] == "High"
    print("[PASS] Test 10: consistency rating classifies correctly")


# ===================================================================
#  Test 11: Behavioral Profile
# ===================================================================

def test_behavioral_profile():
    from dialogue.analytics import generate_behavioral_profile

    strong = [
        {"ownership": 5, "leadership": 4, "structure": 5, "result_orientation": 4,
         "star_breakdown": {"situation_present": True, "task_present": True,
                            "action_present": True, "result_present": True}},
        {"ownership": 4, "leadership": 5, "structure": 4, "result_orientation": 5,
         "star_breakdown": {"situation_present": True, "task_present": True,
                            "action_present": True, "result_present": True}},
    ]
    p1 = generate_behavioral_profile(strong)
    assert p1["ownership_pattern"] == "Strong"
    assert p1["leadership_presence"] == "Strong"
    assert p1["data_orientation"] == "Data-Driven"

    weak = [
        {"ownership": 1, "leadership": 1, "structure": 2, "result_orientation": 1},
        {"ownership": 2, "leadership": 2, "structure": 1, "result_orientation": 2},
    ]
    p2 = generate_behavioral_profile(weak)
    assert p2["ownership_pattern"] == "Weak"
    assert p2["leadership_presence"] == "Minimal"
    assert p2["data_orientation"] == "Vague"

    p3 = generate_behavioral_profile([])
    assert p3["ownership_pattern"] == "N/A"
    print("[PASS] Test 11: behavioral profile derives correctly")


# ===================================================================
#  Run All Tests
# ===================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AI INTERVIEWER -- Full Test Suite (v4.0)")
    print("=" * 60)
    print()

    tests = [
        test_interview_stage,
        test_validate_adaptive_evaluation,
        test_validate_decision,
        test_decide_from_adaptive,
        test_decide_fallback,
        test_previous_evaluations_summary,
        test_weighted_scoring,
        test_star_tracking,
        test_trend_detection,
        test_consistency_rating,
        test_behavioral_profile,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__} ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
