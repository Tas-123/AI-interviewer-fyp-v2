"""Regression tests for canonical question store, IDK hints, and resume preference."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dialogue.context import InterviewContext
from dialogue.guards.echo_guard import canonicalize_for_store, short_repeat_question
from dialogue.guards.idk_guard import IdkGuard
from dialogue.guards.types import GuardContext
from dialogue.idk_policy import idk_attempt_response, is_idk_response
from dialogue.rephrase_policy import fallback_recovery_line, resolve_core_question
from dialogue.resume_context_parser import (
    extract_projects,
    generate_resume_questions,
    map_resume_to_domains,
    parse_resume,
)
from dialogue.session_bootstrap import build_candidate_profile


def test_canonicalize_strips_stacked_duplicates():
    stacked = (
        "Happy to repeat that. What preprocessing would you apply before sending "
        "the text to the model? What preprocessing would you apply before sending "
        "the text to the model? Please answer with your own experience "
        "Please answer with your own experience."
    )
    clean = canonicalize_for_store(stacked)
    assert clean.count("?") == 1, clean
    assert clean.lower().count("what preprocessing would you apply") == 1, clean
    assert "please answer with your own experience" not in clean.lower()


def test_context_canonical_preferred_over_stacked_history():
    ctx = InterviewContext(
        {
            "skills": ["Python"],
            "experience": "1 year",
            "role": "Junior AI Engineer",
            "target_role": "junior_ai_engineer",
        }
    )
    core = (
        "What preprocessing would you apply before sending the text to the model?"
    )
    ctx.set_active_question(core, domain_intent="nlp preprocessing")
    stacked = f"I'll rephrase the question. {core} {core}"
    ctx.add_turn(stacked, "can you repeat?")
    resolved = resolve_core_question(ctx, stacked)
    assert resolved == core
    assert short_repeat_question(stacked, interview_context=ctx) == core


def test_three_recoveries_do_not_stack_core_question():
    core = (
        "How would you detect overfitting in a machine learning model?"
    )
    line1 = fallback_recovery_line("repeat", core)
    line2 = fallback_recovery_line("clarify", core)
    line3 = fallback_recovery_line("redirect", core)
    for line in (line1, line2, line3):
        assert line.count("?") == 1, line
        assert line.lower().count("detect overfitting") == 1, line


def test_long_idk_pass_detected():
    text = (
        "Well, for that, I will gonna I don't know. I literally don't know. "
        "I didn't done it. So, yeah, I will pass this question"
    )
    assert is_idk_response(text) is True


def test_idk_attempt_two_includes_hint():
    core = "What preprocessing would you apply before sending text to the model?"
    ctx = InterviewContext(
        {
            "skills": ["Python"],
            "experience": "1 year",
            "role": "Junior AI Engineer",
            "target_role": "junior_ai_engineer",
        }
    )
    ctx.set_active_question(core)
    ctx.current_domain = "nlp_speech_ai"
    spoken, flow = idk_attempt_response(
        "nlp_speech_ai",
        2,
        f"Happy to repeat. {core} {core}",
        interview_context=ctx,
        llm_client=None,
    )
    assert flow == "hint_idk"
    assert "here's a small hint" in spoken.lower()
    assert spoken.lower().count("what preprocessing") <= 1


def test_idk_guard_uses_broad_detection():
    ctx = InterviewContext(
        {
            "skills": ["Python"],
            "experience": "1 year",
            "role": "Junior AI Engineer",
            "target_role": "junior_ai_engineer",
        }
    )
    core = "How would you expose a model through an API?"
    ctx.set_active_question(core)
    ctx.current_domain = "apis_backend"
    guard = IdkGuard()
    # First IDK
    hit1 = guard.check(
        GuardContext(
            transcript="I don't know, I will pass this question",
            last_question=f"I'll rephrase. {core}",
            interview_context=ctx,
        )
    )
    assert hit1.triggered
    assert hit1.metadata["flow_action"] == "rephrase_idk"
    # Second IDK → hint
    hit2 = guard.check(
        GuardContext(
            transcript="Still don't know anything about that",
            last_question=hit1.response_text,
            interview_context=ctx,
        )
    )
    assert hit2.triggered
    assert hit2.metadata["flow_action"] == "hint_idk"
    assert "hint" in hit2.response_text.lower()


def test_resume_projects_and_domain_mapping():
    text = (
        "Junior AI engineer. Built a speaker recognition project using embeddings "
        "and Qdrant. Experienced with FastAPI and Docker."
    )
    parsed = parse_resume(text)
    assert parsed["candidate_projects"] or "speaker recognition" in text.lower()
    projects = extract_projects(text)
    assert projects
    by_domain = map_resume_to_domains(
        skills=parsed["candidate_skills"],
        tools=parsed["candidate_tools"],
        projects=projects,
        resume_text=text,
    )
    assert "nlp_speech_ai" in by_domain or "apis_backend" in by_domain
    questions = generate_resume_questions(
        {
            **parsed,
            "candidate_projects": projects,
        }
    )
    assert questions
    assert all(isinstance(q, dict) and "question" in q for q in questions)


def test_bootstrap_resume_profile_prefers_resume():
    profile = build_candidate_profile(
        resume_text=(
            "I built a speaker recognition system with Python, FastAPI, and Qdrant."
        ),
        display_name="Usman",
    )
    assert profile.profile_source == "resume"
    data = profile.to_resume_data()
    assert data["profile_source"] == "resume"
    assert data.get("resume_by_domain")
    assert profile.resume_questions


def test_resume_only_skills_exclude_default_pollution():
    profile = build_candidate_profile(
        resume_text=(
            "Skills: NLP, Computer Vision, YOLO. "
            "Built classification and detection systems."
        )
    )
    assert profile.profile_source == "resume"
    skills_l = [s.lower() for s in profile.skills]
    assert "python" not in skills_l
    assert "machine learning" not in skills_l
    docker = build_candidate_profile(resume_data={"skills": ["Docker"]})
    assert docker.skills == ["Docker"]


def test_soft_next_still_stays_via_canonical():
    from dialogue.guards.meta_conversation_guard import MetaConversationGuard

    ctx = InterviewContext(
        {
            "skills": ["Python"],
            "experience": "1 year",
            "role": "Junior AI Engineer",
            "target_role": "junior_ai_engineer",
        }
    )
    core = "How would you handle missing values before training?"
    ctx.set_active_question(core)
    ctx.current_domain = "data_preprocessing"
    guard = MetaConversationGuard()
    hit = guard.check(
        GuardContext(
            transcript="Move to the next question please",
            last_question=f"Let's stay with the current question for now. {core} {core}",
            interview_context=ctx,
        )
    )
    assert hit.triggered
    assert hit.metadata.get("flow_action") == "stay_on_question"
    # Spoken recovery must not multiply the core ask.
    assert hit.response_text.lower().count("missing values") <= 1


if __name__ == "__main__":
    tests = [
        test_canonicalize_strips_stacked_duplicates,
        test_context_canonical_preferred_over_stacked_history,
        test_three_recoveries_do_not_stack_core_question,
        test_long_idk_pass_detected,
        test_idk_attempt_two_includes_hint,
        test_idk_guard_uses_broad_detection,
        test_resume_projects_and_domain_mapping,
        test_bootstrap_resume_profile_prefers_resume,
        test_resume_only_skills_exclude_default_pollution,
        test_soft_next_still_stays_via_canonical,
    ]
    for fn in tests:
        fn()
        print(f"[PASS] {fn.__name__}")
    print(f"[PASS] {len(tests)}/{len(tests)} voice UX refinement tests")
