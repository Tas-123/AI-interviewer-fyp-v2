import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dialogue.guards.pipeline import GuardPipeline
from dialogue.guards.types import GuardContext


def test_pipeline_stops_at_first_guard():
    pipeline = GuardPipeline(llm_client=None, llm_model="test")
    intro_q = (
        "Good morning, welcome to the interview. "
        "Can you start by introducing yourself and tell me about a project?"
    )
    ctx = GuardContext(transcript=intro_q, last_question=intro_q)
    hit = pipeline.run(ctx)
    assert hit is not None
    assert hit.triggered is True
    assert hit.decision_type == "BOT_OR_EXTERNAL_PROMPT_ECHO"


if __name__ == "__main__":
    test_pipeline_stops_at_first_guard()
    print("[PASS] test_pipeline")
