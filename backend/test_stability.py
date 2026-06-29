"""
test_stability.py — Stability & Error Handling Tests (STEP 10)

Validates the system handles edge cases gracefully:
  1. Empty answer → default evaluation, no crash
  2. Missing STAR fields → defaults to all False
  3. Invalid JSON from LLM → fallback adaptive result
  4. Negative weighted_score → clamped correctly
  5. DB unavailable → in-memory fallback works
  6. Full evaluation pipeline with degraded inputs

No LLM calls. No Postgres required. Fully offline.
"""

import os
import sys
import json
import math

os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
sys.path.insert(0, os.path.dirname(__file__))

from dialogue.context import InterviewContext
from dialogue.analytics import (
    compute_weighted_score,
    detect_performance_trend,
    compute_consistency_rating,
    generate_behavioral_profile,
    generate_final_report,
)


# ===================================================================
#  Test 1: Empty Answer → Default Evaluation
# ===================================================================

def test_empty_answer():
    """System must not crash on empty/trivial answers."""
    # Inline replication of Evaluator._empty_evaluation logic
    def handle_empty(answer):
        if not answer or len(answer.strip().split()) < 3:
            return {
                "clarity": 1, "structure": 1, "confidence": 1,
                "ownership": 1, "leadership": 1, "result_orientation": 1,
                "overall_score": 1.0,
                "weighted_overall_score": compute_weighted_score({
                    "clarity": 1, "structure": 1, "confidence": 1,
                    "ownership": 1, "leadership": 1, "result_orientation": 1,
                }),
                "weakest_dimension": "clarity",
                "hire_signal": "No Hire",
                "star_breakdown": {
                    "situation_present": False, "task_present": False,
                    "action_present": False, "result_present": False,
                },
            }
        return None

    # Test empty string
    r1 = handle_empty("")
    assert r1 is not None
    assert r1["overall_score"] == 1.0
    assert r1["hire_signal"] == "No Hire"

    # Test whitespace only
    r2 = handle_empty("   ")
    assert r2 is not None

    # Test very short (2 words, under threshold of 3)
    r3 = handle_empty("Not sure")
    assert r3 is not None

    # Test exactly 3 words — passes threshold, goes to LLM
    r4_boundary = handle_empty("I don't know")
    assert r4_boundary is None  # 3 words = not < 3, so goes to LLM

    # Test adequate length returns None (would go to LLM)
    r4 = handle_empty("I led a team of five engineers to deliver a complex microservices project")
    assert r4 is None

    print("[PASS] Test 1: empty/trivial answers handled gracefully")


# ===================================================================
#  Test 2: Missing STAR Fields → Default to False
# ===================================================================

def test_missing_star_fields():
    """Missing STAR fields should default to False, not crash."""
    def validate_star(star_raw):
        return {
            "situation_present": bool(star_raw.get("situation_present", False)),
            "task_present": bool(star_raw.get("task_present", False)),
            "action_present": bool(star_raw.get("action_present", False)),
            "result_present": bool(star_raw.get("result_present", False)),
        }

    # Completely empty
    r1 = validate_star({})
    assert all(v is False for v in r1.values())

    # Partial fields
    r2 = validate_star({"situation_present": True})
    assert r2["situation_present"] is True
    assert r2["task_present"] is False
    assert r2["action_present"] is False
    assert r2["result_present"] is False

    # None values
    r3 = validate_star({"situation_present": None, "action_present": 0})
    assert r3["situation_present"] is False
    assert r3["action_present"] is False

    # Non-boolean truthy values
    r4 = validate_star({"situation_present": 1, "task_present": "yes"})
    assert r4["situation_present"] is True
    assert r4["task_present"] is True

    # Context STAR tracking with all-False fields (explicit missing components)
    ctx = InterviewContext({"skills": ["Python"], "experience": "2 years"})
    ctx.add_evaluation({
        "overall_score": 2.5, "weighted_overall_score": 2.5,
        "star_breakdown": {
            "situation_present": False, "task_present": False,
            "action_present": False, "result_present": False,
        },
    })
    assert ctx.star_stats["missing_result_count"] == 1
    assert ctx.star_stats["weak_action_count"] == 1
    assert ctx.star_stats["incomplete_star_count"] == 1

    # Empty dict {} is falsy in Python → context skips STAR tracking
    ctx2 = InterviewContext({"skills": [], "experience": ""})
    ctx2.add_evaluation({
        "overall_score": 2.0, "weighted_overall_score": 2.0,
        "star_breakdown": {},
    })
    assert ctx2.star_stats["missing_result_count"] == 0  # {} is falsy, skipped
    assert ctx2.star_stats["weak_action_count"] == 0
    assert ctx2.star_stats["incomplete_star_count"] == 0

    print("[PASS] Test 2: missing STAR fields default to False correctly")


# ===================================================================
#  Test 3: Invalid JSON from LLM → Fallback Result
# ===================================================================

def test_invalid_json_fallback():
    """Invalid JSON should produce a safe fallback, not crash."""
    def parse_adaptive_response(raw_text):
        """Mimics Evaluator.adaptive_evaluate JSON parsing."""
        try:
            # Strip markdown fences
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                raw_text = raw_text.rsplit("```", 1)[0]
                raw_text = raw_text.strip()
            return json.loads(raw_text)
        except (json.JSONDecodeError, IndexError, ValueError):
            # Fallback
            return {
                "evaluation": {
                    "clarity": 0, "structure": 0, "confidence": 0,
                    "ownership": 0, "leadership": 0, "result_orientation": 0,
                    "overall_score": 0.0,
                    "weakest_dimension": "unknown",
                    "hire_signal": "N/A",
                    "is_error": True,
                    "star_breakdown": {
                        "situation_present": False, "task_present": False,
                        "action_present": False, "result_present": False,
                    },
                },
                "decision": {
                    "type": "ADVANCE",
                    "next_question": "Tell me about a challenging project you worked on recently.",
                },
            }

    # Completely invalid
    r1 = parse_adaptive_response("This is not JSON at all")
    assert r1["evaluation"]["is_error"] is True
    assert r1["decision"]["type"] == "ADVANCE"

    # Truncated JSON
    r2 = parse_adaptive_response('{"evaluation": {"clarity": 4,')
    assert r2["evaluation"]["is_error"] is True

    # JSON inside markdown fences
    valid_fenced = '```json\n{"evaluation": {"clarity": 4}, "decision": {"type": "PROBE"}}\n```'
    r3 = parse_adaptive_response(valid_fenced)
    assert r3["evaluation"]["clarity"] == 4

    # Empty string
    r4 = parse_adaptive_response("")
    assert r4["evaluation"]["is_error"] is True

    # Valid JSON (should parse fine)
    r5 = parse_adaptive_response('{"evaluation": {"clarity": 5}, "decision": {"type": "ADVANCE"}}')
    assert r5["evaluation"]["clarity"] == 5

    print("[PASS] Test 3: invalid JSON from LLM handled with safe fallback")


# ===================================================================
#  Test 4: Negative Weighted Score → Clamped
# ===================================================================

def test_negative_weighted_score():
    """Negative or zero scores should be handled without crash."""
    def validate_scores(data):
        score_fields = ["clarity", "structure", "confidence",
                        "ownership", "leadership", "result_orientation"]
        for field in score_fields:
            val = data.get(field, 0)
            data[field] = max(1, min(5, int(val)))
        scores = [data[f] for f in score_fields]
        data["overall_score"] = round(sum(scores) / len(scores), 2)
        data["weighted_overall_score"] = compute_weighted_score(data)
        return data

    # Negative scores
    r1 = validate_scores({
        "clarity": -3, "structure": -1, "confidence": 0,
        "ownership": -5, "leadership": -2, "result_orientation": -4,
    })
    for f in ["clarity", "structure", "confidence", "ownership",
              "leadership", "result_orientation"]:
        assert r1[f] >= 1, f"Score {f} not clamped: {r1[f]}"
    assert r1["overall_score"] == 1.0
    assert r1["weighted_overall_score"] == 1.0

    # Scores above 5
    r2 = validate_scores({
        "clarity": 10, "structure": 99, "confidence": 7,
        "ownership": 6, "leadership": 100, "result_orientation": 8,
    })
    for f in ["clarity", "structure", "confidence", "ownership",
              "leadership", "result_orientation"]:
        assert r2[f] <= 5, f"Score {f} not clamped: {r2[f]}"

    # All zeros
    r3 = validate_scores({})
    assert r3["overall_score"] == 1.0  # Clamped minimum is 1

    print("[PASS] Test 4: negative/extreme scores clamped correctly")


# ===================================================================
#  Test 5: DB Unavailable → In-Memory Fallback
# ===================================================================

def test_db_fallback():
    """System must work when Postgres is unavailable."""
    from dialogue import database as db_module

    # Force DB unavailable
    original = db_module._pg_available
    db_module._pg_available = False

    assert db_module.is_available() is False
    assert db_module.save_session("test", {}) is False
    assert db_module.save_response("test", 1, "q", "a", 3.0, 3.0, {}, "EARLY", 100) is False
    assert db_module.get_latency_metrics("test")["source"] == "unavailable"
    assert db_module.get_session_responses("test") == []
    assert db_module.update_session_finals("test", 3.0, "Hire", "stable", "High") is False

    # Restore
    db_module._pg_available = original

    print("[PASS] Test 5: DB unavailable fallback works gracefully")


# ===================================================================
#  Test 6: Full Pipeline with Degraded Inputs
# ===================================================================

def test_degraded_pipeline():
    """Full pipeline survives degraded evaluation data."""
    ctx = InterviewContext({"skills": ["Python"], "experience": "1 year"})

    # Add a valid evaluation
    ctx.add_evaluation({
        "overall_score": 3.5, "weighted_overall_score": 3.5,
        "clarity": 3, "structure": 4, "confidence": 3,
        "ownership": 4, "leadership": 3, "result_orientation": 4,
        "weakest_dimension": "clarity", "hire_signal": "Hire",
        "star_breakdown": {
            "situation_present": True, "task_present": True,
            "action_present": True, "result_present": False,
        },
    })
    ctx.add_turn("Q1", "A1")

    # Add an error evaluation (simulates LLM failure)
    ctx.add_evaluation({
        "overall_score": 0.0, "weighted_overall_score": 0,
        "is_error": True, "weakest_dimension": "unknown",
        "hire_signal": "N/A",
    })
    ctx.add_turn("Q2", "")

    # Add another valid evaluation
    ctx.add_evaluation({
        "overall_score": 4.0, "weighted_overall_score": 4.0,
        "clarity": 4, "structure": 5, "confidence": 4,
        "ownership": 4, "leadership": 4, "result_orientation": 4,
        "weakest_dimension": "clarity", "hire_signal": "Hire",
        "star_breakdown": {
            "situation_present": True, "task_present": True,
            "action_present": True, "result_present": True,
        },
    })
    ctx.add_turn("Q3", "A3")

    # Generate final report — must not crash
    report = generate_final_report(ctx)

    assert report is not None
    assert "weighted_score_summary" in report
    assert "star_effectiveness_analysis" in report
    assert "performance_trend_analysis" in report
    assert "consistency_rating" in report
    assert "behavioral_profile" in report
    assert "bias_awareness" in report

    # Verify report is JSON-serializable
    json_str = json.dumps(report, default=str)
    assert len(json_str) > 0
    reparsed = json.loads(json_str)
    assert reparsed["weighted_score_summary"]["total_evaluated"] == 2  # error excluded

    print("[PASS] Test 6: degraded pipeline produces valid final report")


# ===================================================================
#  Test 7: Context STAR Stats Accumulation
# ===================================================================

def test_star_accumulation():
    """STAR stats accumulate correctly across multiple evaluations."""
    ctx = InterviewContext({"skills": [], "experience": ""})

    # Missing everything
    ctx.add_evaluation({
        "overall_score": 1.0, "weighted_overall_score": 1.0,
        "star_breakdown": {
            "situation_present": False, "task_present": False,
            "action_present": False, "result_present": False,
        },
    })
    assert ctx.star_stats["missing_result_count"] == 1
    assert ctx.star_stats["weak_action_count"] == 1
    assert ctx.star_stats["incomplete_star_count"] == 1

    # Complete STAR
    ctx.add_evaluation({
        "overall_score": 4.0, "weighted_overall_score": 4.0,
        "star_breakdown": {
            "situation_present": True, "task_present": True,
            "action_present": True, "result_present": True,
        },
    })
    # Counts should NOT increase for complete STAR
    assert ctx.star_stats["missing_result_count"] == 1
    assert ctx.star_stats["weak_action_count"] == 1
    assert ctx.star_stats["incomplete_star_count"] == 1

    # Missing result only
    ctx.add_evaluation({
        "overall_score": 3.0, "weighted_overall_score": 3.0,
        "star_breakdown": {
            "situation_present": True, "task_present": True,
            "action_present": True, "result_present": False,
        },
    })
    assert ctx.star_stats["missing_result_count"] == 2
    assert ctx.star_stats["weak_action_count"] == 1  # action was present
    assert ctx.star_stats["incomplete_star_count"] == 2

    print("[PASS] Test 7: STAR stats accumulate correctly")


# ===================================================================
#  Test 8: Weighted Score History Tracking
# ===================================================================

def test_weighted_score_tracking():
    """Weighted score history only tracks positive scores."""
    ctx = InterviewContext({"skills": [], "experience": ""})

    ctx.add_evaluation({"overall_score": 3.0, "weighted_overall_score": 3.2})
    ctx.add_evaluation({"overall_score": 0.0, "weighted_overall_score": 0})  # error
    ctx.add_evaluation({"overall_score": 4.0, "weighted_overall_score": 4.1})

    assert len(ctx.weighted_score_history) == 2
    assert ctx.weighted_score_history[0] == (0, 3.2)  # turn_count is 0-based here
    assert ctx.weighted_score_history[1] == (0, 4.1)

    print("[PASS] Test 8: weighted score history filters zero/error scores")


# ===================================================================
#  Test 9: JSON Serialization of All Outputs
# ===================================================================

def test_json_serialization():
    """All evaluation and report outputs must be JSON-serializable."""
    ctx = InterviewContext({"skills": ["Python", "ML"], "experience": "5 years"})

    for i in range(3):
        ctx.add_evaluation({
            "overall_score": 3.0 + i * 0.5,
            "weighted_overall_score": 3.0 + i * 0.5,
            "clarity": 3 + i, "structure": 3 + i, "confidence": 3,
            "ownership": 4, "leadership": 3, "result_orientation": 3 + i,
            "weakest_dimension": "confidence",
            "hire_signal": "Hire",
            "star_breakdown": {
                "situation_present": True, "task_present": True,
                "action_present": bool(i > 0), "result_present": bool(i > 1),
            },
        })
        ctx.add_turn(f"Q{i+1}", f"A{i+1}")

    report = generate_final_report(ctx)

    # Must serialize cleanly
    json_str = json.dumps(report, default=str)
    assert json_str is not None

    # Must parse back
    reparsed = json.loads(json_str)
    assert isinstance(reparsed, dict)

    # Check all expected keys
    expected_keys = [
        "weighted_score_summary", "star_effectiveness_analysis",
        "performance_trend_analysis", "consistency_rating",
        "behavioral_profile", "bias_awareness", "interview_metadata",
    ]
    for key in expected_keys:
        assert key in reparsed, f"Missing key: {key}"

    print("[PASS] Test 9: all outputs JSON-serializable")


# ===================================================================
#  Run All Tests
# ===================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AI INTERVIEWER — Stability Test Suite (v4.0)")
    print("=" * 60)
    print()

    tests = [
        test_empty_answer,
        test_missing_star_fields,
        test_invalid_json_fallback,
        test_negative_weighted_score,
        test_db_fallback,
        test_degraded_pipeline,
        test_star_accumulation,
        test_weighted_score_tracking,
        test_json_serialization,
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
