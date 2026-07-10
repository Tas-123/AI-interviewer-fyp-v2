"""Phase 5 — VoiceTurnPolicy and config-driven timing tests."""

from __future__ import annotations

from dataclasses import replace

from core.config import settings
from voice.voice_turn_policy import VoiceTurnPolicy, DEFAULT_FILLER_WORDS


def test_from_settings_reads_debounce():
    cfg = replace(
        settings,
        transcript_debounce_seconds=4.5,
        short_answer_grace_seconds=3.0,
    )
    policy = VoiceTurnPolicy.from_settings(cfg)
    assert policy.transcript_debounce_seconds == 4.5
    assert policy.short_answer_grace_seconds == 3.0


def test_is_filler():
    policy = VoiceTurnPolicy(
        transcript_debounce_seconds=3.0,
        short_answer_grace_seconds=2.5,
        short_answer_word_threshold=6,
        startup_audio_gate_seconds=4.0,
        startup_refresh_seconds=3.0,
        bot_echo_cooldown_seconds=1.2,
        bot_stop_echo_cooldown_seconds=0.8,
        closing_delay_seconds=2.5,
            candidate_silence_nudge_seconds=8.0,
            candidate_silence_rephrase_seconds=15.0,
            barge_in_min_bot_speak_seconds=0.25,
            final_transcript_debounce_seconds=0.35,
            filler_words=DEFAULT_FILLER_WORDS,
        )
    assert policy.is_filler("ok")
    assert policy.is_filler("  Yeah! ")
    assert not policy.is_filler("I built a chatbot with Python")


def test_is_short_answer():
    policy = VoiceTurnPolicy(
        transcript_debounce_seconds=3.0,
        short_answer_grace_seconds=2.5,
        short_answer_word_threshold=6,
        startup_audio_gate_seconds=4.0,
        startup_refresh_seconds=3.0,
        bot_echo_cooldown_seconds=1.2,
        bot_stop_echo_cooldown_seconds=0.8,
        closing_delay_seconds=2.5,
        candidate_silence_nudge_seconds=8.0,
        candidate_silence_rephrase_seconds=15.0,
        barge_in_min_bot_speak_seconds=0.25,
        final_transcript_debounce_seconds=0.35,
        filler_words=DEFAULT_FILLER_WORDS,
    )
    assert policy.is_short_answer("Worked on a small NLP project")
    assert not policy.is_short_answer(
        "I worked on a small NLP project using transformers and deployed it to production"
    )


def test_strip_followup_prefix():
    from dialogue.output_sanitizer import strip_followup_prefix

    assert strip_followup_prefix("[Follow-up] What tradeoffs did you consider?") == (
        "What tradeoffs did you consider?"
    )


if __name__ == "__main__":
    try:
        import pytest
        raise SystemExit(pytest.main([__file__, "-q"]))
    except ImportError:
        test_from_settings_reads_debounce()
        test_is_filler()
        test_is_short_answer()
        test_strip_followup_prefix()
        print("[PASS] voice turn policy tests (no pytest)")
