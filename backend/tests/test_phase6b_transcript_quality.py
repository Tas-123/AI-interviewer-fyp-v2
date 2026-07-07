"""
Phase 6B — Transcript cleanup, noisy STT detection, evaluation fairness.
"""

from __future__ import annotations

from dialogue.transcript_quality import assess_transcript_quality
from dialogue.transcript_utils import clean_live_transcript, prepare_transcript_for_evaluation
from evaluation.rubric import apply_transcript_quality_adjustment, compute_weighted_score


def test_removes_stutter_prefix():
    raw = (
        "Well, I Well, I worked on a classification project using Random Forest "
        "and evaluated with accuracy."
    )
    cleaned = clean_live_transcript(raw)
    assert cleaned.lower().startswith("well, i worked")
    assert cleaned.count("Well, I") == 1


def test_detects_noisy_repeated_stt():
    raw = (
        "I use Python I use Python I use Python for preprocessing and "
        "I use Python for preprocessing and model training."
    )
    cleaned = clean_live_transcript(raw)
    quality = assess_transcript_quality(raw, cleaned)
    assert quality.is_noisy or quality.noise_score >= 0.35
    assert "repeated_tokens" in quality.flags or quality.reduction_ratio > 0


def test_prepare_transcript_for_evaluation_returns_quality():
    raw = "I don't know I don't know I don't know about overfitting."
    cleaned, quality = prepare_transcript_for_evaluation(raw)
    assert cleaned
    assert quality.raw_word_count >= quality.cleaned_word_count
    assert isinstance(quality.to_dict(), dict)


def test_noisy_transcript_reduces_communication_weight_penalty():
    evaluation = {
        "clarity": 1.0,
        "structure": 1.5,
        "confidence": 2.0,
        "ownership": 4.0,
        "leadership": 3.5,
        "result_orientation": 4.0,
        "overall_score": 3.0,
        "weighted_overall_score": compute_weighted_score({
            "clarity": 1.0,
            "structure": 1.5,
            "confidence": 2.0,
            "ownership": 4.0,
            "leadership": 3.5,
            "result_orientation": 4.0,
        }),
        "hire_signal": "Borderline",
    }
    baseline = evaluation["weighted_overall_score"]
    adjusted = apply_transcript_quality_adjustment(
        evaluation,
        {"is_noisy": True, "noise_score": 0.55, "flags": ["repeated_tokens"]},
    )
    assert adjusted["transcript_quality_adjusted"] is True
    assert adjusted["weighted_overall_score"] >= baseline


if __name__ == "__main__":
    test_removes_stutter_prefix()
    test_detects_noisy_repeated_stt()
    test_prepare_transcript_for_evaluation_returns_quality()
    test_noisy_transcript_reduces_communication_weight_penalty()
    print("[PASS] test_phase6b_transcript_quality")
