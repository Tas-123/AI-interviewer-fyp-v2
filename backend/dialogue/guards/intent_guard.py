"""Intent guard — classifies candidate utterances before evaluation."""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

from dialogue.guards.echo_guard import short_repeat_question
from dialogue.guards.incomplete_guard import looks_like_incomplete_transcript
from dialogue.guards.types import GuardContext, GuardResult


def classify_candidate_intent(
    transcript: str,
    last_question: str = "",
    *,
    llm_client=None,
    llm_model: str = "",
) -> str:
    """
    Classify candidate utterance before evaluation.

    Returns one of:
    ANSWER_ATTEMPT, REPEAT_REQUEST, CLARIFICATION_REQUEST,
    AUDIO_ISSUE, OFF_TOPIC, EXTERNAL_PROMPT_ECHO
    """
    text = (transcript or "").strip().lower()
    if not text:
        return "AUDIO_ISSUE"

    clean = text.strip(" .,!?'\"").lower()
    words = clean.split()

    audio_issue_phrases = [
        "hello", "hello?", "can you hear me", "are you there",
        "can't hear you", "cant hear you", "i can't hear you", "i cant hear you",
        "i could not hear", "could not hear", "couldn't hear", "i didn't hear",
        "i didnt hear", "not audible", "voice is low", "your voice is low",
        "audio issue", "mic issue",
    ]
    repeat_phrases = [
        "repeat", "repeat the question", "can you repeat", "please repeat",
        "say that again", "say it again", "ask again", "question again",
        "come again", "pardon",
    ]
    clarification_phrases = [
        "what do you mean", "what does that mean", "i don't understand",
        "i dont understand", "i did not understand", "didn't understand",
        "didnt understand", "couldn't understand", "couldnt understand",
        "i couldn't understand", "i couldnt understand",
        "sorry i couldn't understand", "sorry i couldnt understand",
        "can you explain", "please explain", "clarify",
        "can you clarify", "about what", "which one", "which model",
        "what model", "specific model", "what specific model",
        "what specific model are you talking about",
    ]
    external_prompt_phrases = [
        "i don't want buzzwords", "i dont want buzzwords",
        "don't want buzzwords", "dont want buzzwords",
        "skip the general stuff", "don't just throw general techniques",
        "dont just throw general techniques",
        "tell me exactly", "be practical", "not theoretical",
        "give me a structure you'd actually implement",
        "give me a structure you would actually implement",
        "before you start", "keep it specific",
        "generic intro", "focus on a concrete project",
        "what you actually did", "why it was impactful",
        "i want a clear set of steps", "go.",
    ]
    skip_phrases = [
        "move to the next question", "move to next question",
        "go to the next question", "next question please",
        "can we move to the next", "skip this question",
        "don't have answer", "dont have answer",
        "don't have an answer", "dont have an answer",
    ]
    off_topic_phrases = [
        "let's talk about something else", "lets talk about something else",
        "i don't want this interview", "i dont want this interview",
        "change the topic", "leave this question",
        "i am not here for", "i'm not here for",
        "what do you mean by how",
    ]

    if any(p in clean for p in audio_issue_phrases):
        return "AUDIO_ISSUE"
    if any(p in clean for p in repeat_phrases):
        return "REPEAT_REQUEST"
    if any(p in clean for p in clarification_phrases):
        return "CLARIFICATION_REQUEST"
    if any(p in clean for p in external_prompt_phrases):
        return "EXTERNAL_PROMPT_ECHO"
    if any(p in clean for p in skip_phrases):
        return "SKIP_REQUEST"
    if any(p in clean for p in off_topic_phrases):
        return "OFF_TOPIC"

    if clean.endswith("?") and len(words) <= 10:
        return "CLARIFICATION_REQUEST"

    vague_short = {
        "yes", "no", "okay", "ok", "yeah", "hmm", "um", "uh",
        "what", "why", "how", "about what",
    }
    if clean in vague_short:
        return "CLARIFICATION_REQUEST"

    instruction_markers = [
        "tell me", "give me", "walk me through", "i want", "don't", "dont",
        "focus on", "be specific", "be practical", "skip",
    ]
    answer_markers = [
        "i built", "i worked", "i used", "i implemented", "i created",
        "i trained", "i evaluated", "my project", "my model", "we built",
        "we used", "python", "machine learning", "model", "dataset",
        "accuracy", "precision", "recall", "api", "deployment",
    ]

    if sum(1 for p in instruction_markers if p in clean) >= 2 and not any(
        p in clean for p in answer_markers
    ):
        return "EXTERNAL_PROMPT_ECHO"

    if looks_like_incomplete_transcript(transcript, last_question):
        return "ANSWER_ATTEMPT"

    if should_use_semantic_intent_classifier(transcript):
        return semantic_intent_classify(
            transcript, last_question, llm_client=llm_client, llm_model=llm_model
        )

    return "ANSWER_ATTEMPT"


def should_use_semantic_intent_classifier(transcript: str) -> bool:
    """Use LLM intent classifier only for ambiguous utterances."""
    text = (transcript or "").strip().lower()
    if not text:
        return False

    words = text.split()
    if len(words) <= 12:
        return True
    if "?" in text:
        return True

    ambiguous_markers = [
        "sorry", "not sure", "i missed", "missed that", "say it another way",
        "frame it differently", "are you asking", "do you mean", "which part",
        "which one", "what angle", "your voice", "voice cut", "audio", "mic",
    ]
    if any(marker in text for marker in ambiguous_markers):
        return True

    instruction_markers = [
        "tell me exactly", "be specific", "keep it specific", "don't want",
        "dont want", "skip the general", "not theoretical", "be practical",
        "focus on", "walk me through",
    ]
    return any(marker in text for marker in instruction_markers)


def semantic_intent_classify(
    transcript: str,
    last_question: str = "",
    *,
    llm_client=None,
    llm_model: str = "",
) -> str:
    """LLM fallback classifier for candidate intent."""
    allowed = {
        "ANSWER_ATTEMPT", "REPEAT_REQUEST", "CLARIFICATION_REQUEST",
        "AUDIO_ISSUE", "OFF_TOPIC", "EXTERNAL_PROMPT_ECHO",
    }

    if llm_client is None:
        return "ANSWER_ATTEMPT"

    prompt = f"""
You are an intent classifier for a live AI job interview.

Classify the candidate utterance into exactly one label:

ANSWER_ATTEMPT:
The candidate is trying to answer the interview question.

REPEAT_REQUEST:
The candidate asks to repeat the question.

CLARIFICATION_REQUEST:
The candidate asks what the question means.

AUDIO_ISSUE:
The candidate reports audio or connection problems.

OFF_TOPIC:
The candidate talks about something unrelated.

EXTERNAL_PROMPT_ECHO:
The transcript sounds like an interviewer or coach instructing someone how to answer.

Current interview question:
{last_question}

Candidate utterance:
{transcript}

Return JSON only:
{{"intent":"LABEL","confidence":0.0}}
""".strip()

    try:
        response = llm_client.chat.completions.create(
            model=llm_model or "llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return only valid JSON. No explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=60,
        )
        content = response.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)
        data = json.loads(content)
        intent = str(data.get("intent", "ANSWER_ATTEMPT")).strip().upper()
        confidence = float(data.get("confidence", 0))
        if intent in allowed and confidence >= 0.55:
            return intent
    except Exception as exc:
        logger.warning("Semantic fallback failed: %s", exc)

    return "ANSWER_ATTEMPT"


def intent_redirect_response(
    intent: str, transcript: str, last_question: str = ""
) -> str:
    """Generate a no-score redirect based on classified candidate intent."""
    last_question = (last_question or "").strip()
    repeat_q = short_repeat_question(last_question)

    if intent == "REPEAT_REQUEST":
        return f"Sure, I'll repeat the question. {repeat_q}"

    if intent == "AUDIO_ISSUE":
        return f"No problem, I'll repeat it clearly. {repeat_q}"

    if intent == "CLARIFICATION_REQUEST":
        t_clean = (transcript or "").lower()
        if any(phrase in t_clean for phrase in ["understand", "not clear", "unclear"]):
            return f"Sure, I'll repeat the question. {repeat_q}"
        return (
            "I'll rephrase the question. "
            f"{repeat_q} "
            "Please answer with your own experience."
        )

    if intent == "SKIP_REQUEST":
        return "Sure — let's move on to a different area of the interview."

    if intent == "OFF_TOPIC":
        return (
            "Let's stay focused on the interview. "
            f"Please answer this question directly: {repeat_q}"
        )

    if intent == "EXTERNAL_PROMPT_ECHO":
        return (
            "I may have captured an instruction or external prompt instead of your answer. "
            f"Please answer the current interview question directly: {repeat_q}"
        )

    return f"Please answer the current interview question directly: {repeat_q}"


class IntentGuard:
    """Guard that redirects non-answer intents without scoring."""

    name = "intent"

    def __init__(self, llm_client=None, llm_model: str = ""):
        self._llm_client = llm_client
        self._llm_model = llm_model

    def check(self, ctx: GuardContext) -> GuardResult:
        intent = classify_candidate_intent(
            ctx.transcript,
            ctx.last_question,
            llm_client=ctx.llm_client or self._llm_client,
            llm_model=ctx.llm_model or self._llm_model,
        )
        if intent == "ANSWER_ATTEMPT":
            return GuardResult(triggered=False)

        metadata = {"guard": self.name, "intent": intent}
        if intent == "SKIP_REQUEST":
            metadata["flow_action"] = "skip_domain"

        return GuardResult(
            triggered=True,
            decision_type=intent,
            response_text=intent_redirect_response(
                intent, ctx.transcript, ctx.last_question
            ),
            should_evaluate=False,
            metadata=metadata,
        )
