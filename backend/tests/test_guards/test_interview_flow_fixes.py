import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.guards.echo_guard import canonical_interview_question, short_repeat_question
from dialogue.guards.intent_guard import classify_candidate_intent
from dialogue.guards.meta_conversation_guard import classify_meta_intent
from dialogue.guards.domain_guard import domain_relevance_redirect_response
from dialogue.transcript_utils import clean_live_transcript


def test_canonical_question_strips_stacked_redirects():
    nested = (
        "Let's stay on the current interview question. Your last response did not clearly "
        "answer what I asked. Please answer this directly: Let's stay focused on the interview. "
        "Please answer this question directly: Can you give a specific example of preprocessing?"
    )
    core = canonical_interview_question(nested)
    assert "let's stay" not in core.lower()
    assert core.endswith("preprocessing?")


def test_skip_next_question_not_off_topic():
    assert classify_meta_intent("Can we move to the next question, please?") == "CHANGE_TOPIC"
    assert classify_candidate_intent("Can we move to the next question, please?") == "SKIP_REQUEST"


def test_domain_redirect_uses_canonical_question():
    nested = (
        "Let's come back to this. "
        "How would you handle missing values?"
    )
    response = domain_relevance_redirect_response(nested)
    assert response.count("Let's come back to this.") == 1
    assert "How would you handle missing values?" in response
    assert "Please answer this directly" not in response


def test_collapse_progressive_interim_phrases():
    raw = (
        "was doing was doing a project on ASR in which we was doing a project on ASR "
        "in which we use a model for embeddings"
    )
    cleaned = clean_live_transcript(raw)
    assert cleaned.lower().count("was doing a project on asr") == 1


if __name__ == "__main__":
    test_canonical_question_strips_stacked_redirects()
    test_skip_next_question_not_off_topic()
    test_domain_redirect_uses_canonical_question()
    test_collapse_progressive_interim_phrases()
    print("[PASS] test_interview_flow_fixes")
