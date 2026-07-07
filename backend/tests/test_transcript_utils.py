"""Tests for shared transcript cleanup."""

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.transcript_utils import clean_live_transcript


def test_removes_adjacent_repeated_phrases():
    raw = (
        "I worked on a classification project I worked on a classification project "
        "using Random Forest."
    )
    cleaned = clean_live_transcript(raw)
    assert cleaned.count("I worked on a classification project") == 1


def test_preserves_meaningful_short_answer():
    raw = "I detect overfitting by comparing training and validation scores."
    assert clean_live_transcript(raw) == raw


def test_stutter_prefix_cleanup():
    raw = "Well, I Well, I use pandas for cleaning data."
    cleaned = clean_live_transcript(raw)
    assert cleaned.count("Well, I") == 1


if __name__ == "__main__":
    test_removes_adjacent_repeated_phrases()
    test_preserves_meaningful_short_answer()
    test_stutter_prefix_cleanup()
    print("[PASS] test_transcript_utils")
