"""
Phase 4 tests — rubric, ensemble pipeline, human study export.
"""

import os
import sys
from unittest.mock import MagicMock, patch

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault("GROQ_API_KEY", "mock-key")

from evaluation.rubric import (
    DIMENSION_WEIGHTS,
    compute_weighted_score,
    derive_hire_signal,
    merge_evaluations,
    should_trigger_rethink,
    get_evaluation_methodology,
)
from evaluation.human_study_export import extract_rows_from_report, export_to_csv, export_to_json
from dialogue.evaluation_pipeline import EvaluationPipeline


def test_rubric_weights_sum_to_one():
    assert round(sum(DIMENSION_WEIGHTS.values()), 2) == 1.0
    print("[PASS] test_rubric_weights_sum_to_one")


def test_compute_weighted_score():
    scores = {
        "clarity": 4, "structure": 4, "confidence": 3,
        "ownership": 3, "leadership": 3, "result_orientation": 4,
    }
    ws = compute_weighted_score(scores)
    assert 3.0 <= ws <= 4.0
    print("[PASS] test_compute_weighted_score")


def test_derive_hire_signal():
    assert derive_hire_signal(4.5) == "Strong Hire"
    assert derive_hire_signal(4.0) == "Strong Hire"
    assert derive_hire_signal(3.5) == "Hire"
    assert derive_hire_signal(3.0) == "Hire"
    assert derive_hire_signal(2.8) == "Borderline"
    assert derive_hire_signal(2.0) == "No Hire"
    print("[PASS] test_derive_hire_signal")


def test_should_trigger_rethink_borderline():
    assert should_trigger_rethink({"weighted_overall_score": 3.0})
    assert not should_trigger_rethink({"weighted_overall_score": 4.5})
    print("[PASS] test_should_trigger_rethink_borderline")


def test_should_trigger_rethink_spread():
    assert should_trigger_rethink({
        "weighted_overall_score": 4.0,
        "clarity": 5, "structure": 5, "confidence": 5,
        "ownership": 2, "leadership": 2, "result_orientation": 2,
    })
    print("[PASS] test_should_trigger_rethink_spread")


def test_merge_evaluations():
    primary = {
        "clarity": 2.0, "structure": 3.0, "confidence": 3.0,
        "ownership": 3.0, "leadership": 3.0, "result_orientation": 3.0,
        "strengths": ["Clear"], "weaknesses": ["Shallow"],
        "star_breakdown": {"situation_present": False, "task_present": False,
                           "action_present": True, "result_present": False},
    }
    rethink = {
        "clarity": 3.0, "structure": 3.0, "confidence": 3.0,
        "ownership": 3.0, "leadership": 3.0, "result_orientation": 3.0,
        "strengths": ["Relevant"], "weaknesses": [],
        "star_breakdown": {"situation_present": True, "task_present": False,
                           "action_present": True, "result_present": False},
    }
    merged = merge_evaluations(primary, rethink)
    assert merged["clarity"] == 2.5
    assert merged["ensemble_merged"] is True
    assert merged["weighted_overall_score"] > 0
    print("[PASS] test_merge_evaluations")


def test_evaluation_methodology_metadata():
    meta = get_evaluation_methodology()
    assert meta["rubric_version"] == "1.0"
    assert "dimension_weights" in meta
    assert "ensemble" in meta
    print("[PASS] test_evaluation_methodology_metadata")


def test_pipeline_skips_rethink_when_clear():
    evaluator = MagicMock()
    evaluator._run_primary_adaptive.return_value = {
        "evaluation": {
            "clarity": 4, "structure": 4, "confidence": 4,
            "ownership": 4, "leadership": 4, "result_orientation": 4,
            "overall_score": 4.0, "weighted_overall_score": 4.0,
            "weakest_dimension": "clarity", "hire_signal": "Hire",
            "strengths": [], "weaknesses": [],
            "star_breakdown": {},
        },
        "decision": {"type": "ADVANCE", "next_question": "Next?"},
        "latency_ms": 100,
    }
    pipeline = EvaluationPipeline(evaluator)
    result = pipeline.evaluate_turn("Q", "A long enough answer here.", [], "EARLY")
    assert result["evaluation_method"]["rethink_applied"] is False
    evaluator.rethink_evaluation.assert_not_called()
    print("[PASS] test_pipeline_skips_rethink_when_clear")


def test_pipeline_applies_rethink_when_borderline():
    evaluator = MagicMock()
    evaluator._run_primary_adaptive.return_value = {
        "evaluation": {
            "clarity": 3, "structure": 3, "confidence": 3,
            "ownership": 3, "leadership": 3, "result_orientation": 3,
            "overall_score": 3.0, "weighted_overall_score": 3.0,
            "weakest_dimension": "clarity", "hire_signal": "Borderline",
            "strengths": [], "weaknesses": [],
            "star_breakdown": {},
        },
        "decision": {"type": "PROBE", "next_question": "Follow up?"},
        "latency_ms": 120,
    }
    evaluator.rethink_evaluation.return_value = {
        "evaluation": {
            "clarity": 3.5, "structure": 3.5, "confidence": 3.5,
            "ownership": 3.5, "leadership": 3.5, "result_orientation": 3.5,
            "strengths": [], "weaknesses": [],
            "star_breakdown": {},
        },
        "latency_ms": 90,
    }
    pipeline = EvaluationPipeline(evaluator)
    result = pipeline.evaluate_turn("Q", "A reasonable technical answer with details.", [], "MID")
    assert result["evaluation_method"]["rethink_applied"] is True
    assert result["evaluation"]["ensemble_merged"] is True
    print("[PASS] test_pipeline_applies_rethink_when_borderline")


def test_human_study_export_from_report(tmp_path=None):
    report = {
        "adaptive_questioning_trace": [
            {
                "turn": 1,
                "domain": "python",
                "question_answered": "Explain Python project structure.",
                "candidate_answer": "I use modules and tests.",
                "guard_passed": True,
                "weakest_dimension": "structure",
                "hire_signal": "Borderline",
                "scores": {
                    "clarity": 3, "structure": 2.5, "confidence": 3,
                    "ownership": 3, "leadership": 2, "result_orientation": 2.5,
                    "overall_score": 2.67, "weighted_overall_score": 2.8,
                },
                "evaluation_method": {"rethink_applied": True},
            }
        ]
    }
    rows = extract_rows_from_report(report)
    assert len(rows) == 1
    assert rows[0]["human_rating_overall"] == ""

    from pathlib import Path
    out = Path(backend_dir) / "reports" / "_test_human_study"
    csv_p = export_to_csv(rows, out / "study.csv")
    json_p = export_to_json(rows, out / "study.json")
    assert csv_p.exists()
    assert json_p.exists()
    print("[PASS] test_human_study_export_from_report")


if __name__ == "__main__":
    tests = [
        test_rubric_weights_sum_to_one,
        test_compute_weighted_score,
        test_derive_hire_signal,
        test_should_trigger_rethink_borderline,
        test_should_trigger_rethink_spread,
        test_merge_evaluations,
        test_evaluation_methodology_metadata,
        test_pipeline_skips_rethink_when_clear,
        test_pipeline_applies_rethink_when_borderline,
        test_human_study_export_from_report,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1
    sys.exit(1 if failed else 0)
