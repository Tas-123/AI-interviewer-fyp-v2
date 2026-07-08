"""Phase 6 — extension-aware STT transcript aggregation."""

from __future__ import annotations

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.transcript_utils import clean_live_transcript, merge_stt_hypothesis


def test_progressive_interim_replaces_not_appends():
    a = "My name is"
    b = "My name is Muhammad"
    c = "My name is Muhammad Usman"
    merged = merge_stt_hypothesis(a, b)
    assert merged == b
    merged = merge_stt_hypothesis(merged, c)
    assert merged == c
    assert merged.lower().count("my name is") == 1


def test_near_duplicate_fragments_do_not_double():
    a = "I will use"
    b = "I will use Python for preprocessing"
    assert merge_stt_hypothesis(a, b) == b
    # Same meaning, punctuation differ
    a2 = "I will use,"
    b2 = "I will use Python"
    out = merge_stt_hypothesis(a2, b2)
    assert out.lower().count("i will use") == 1


def test_boundary_overlap_extends():
    a = "I applied standard scaling"
    b = "scaling to numerical features"
    out = merge_stt_hypothesis(a, b)
    assert "standard scaling to numerical" in out.lower()
    assert out.lower().count("scaling") == 1


def test_genuinely_new_clause_still_appends():
    a = "I worked on NLP."
    b = "Then I evaluated with F1."
    out = merge_stt_hypothesis(a, b)
    assert "worked on nlp" in out.lower()
    assert "evaluated with f1" in out.lower()


def test_cleanup_after_bad_legacy_concat():
    messy = (
        "My name is Muhammad Usman My name is Muhammad Usman "
        "and I am applying for ML engineer"
    )
    cleaned = clean_live_transcript(messy)
    assert cleaned.lower().count("my name is") == 1


if __name__ == "__main__":
    test_progressive_interim_replaces_not_appends()
    test_near_duplicate_fragments_do_not_double()
    test_boundary_overlap_extends()
    test_genuinely_new_clause_still_appends()
    test_cleanup_after_bad_legacy_concat()
    print("[PASS] test_phase6_transcript_aggregation")
