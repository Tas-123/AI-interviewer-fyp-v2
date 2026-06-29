# Dialogue Pipeline (Phase 2)

## Turn flow

```
transcript
  → clean_live_transcript()
  → GuardPipeline
       1. EchoGuard
       2. IntentGuard
       3. IncompleteGuard
       4. DomainGuard
  → Evaluator.adaptive_evaluate()
  → DecisionEngine.decide_from_adaptive()
       └── followup_policy.classify_followup_type()
  → LLMAdapter.generate()
       └── output_sanitizer.sanitize_interviewer_output()
```

## Interviewer mode

The system **asks, evaluates, and redirects**. It does not coach or provide example answers.

Persona rules live in `backend/core/interviewer_policy.py` and are injected into `backend/dialogue/prompts.py`.

## Follow-up types

| Type | Meaning |
|------|---------|
| `rationale` | Probe missing reasoning |
| `elaboration` | Request more depth on a weak dimension |
| `clarification` | Repair very short/vague answers |
| `advance` | Move to next blueprint domain |

## Primary runtime

Voice interviews: `python backend/pipecat_integration/interview_bot.py`

REST testing: `uvicorn main:app --reload`
