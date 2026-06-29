# Performance Notes (Phase 5)

## Async Groq calls in the voice path

**Problem:** `InterviewDialogueAdapter.process_user_text()` is synchronous and calls Groq inside `DialogueManager.handle_turn()`. Running it directly in Pipecat's async event loop blocked STT/TTS frame processing.

**Fix:** `InterviewProcessor._submit_turn()` wraps the adapter call in `asyncio.to_thread()` so the event loop stays responsive during LLM evaluation and question generation.

## Log volume

**Problem:** `InterviewProcessor.process_frame()` logged at `INFO` for every frame (~30+ lines per second during live audio).

**Fix:** Per-frame logs moved to `DEBUG`. Enable with `PROCESSOR_LOG_FRAMES=true` or `LOG_LEVEL=DEBUG`. Bot audio chunk deserialization logs demoted to `DEBUG` in `interview_bot.py`.

## Config-driven debounce

Hardcoded `3.0` / `2.5` second sleeps replaced by `VoiceTurnPolicy` fields sourced from `core/config.py`. Tune without code changes via `.env`.

## Evaluation model alignment

`Evaluator` and `LLMAdapter` both read from `core.config.settings`, eliminating the previous mismatch (`llama-3.1-8b-instant` in evaluator vs `llama-3.3-70b-versatile` in config).

## Recommended demo settings

For stable live demos:

```env
LOG_LEVEL=INFO
PROCESSOR_LOG_FRAMES=false
DEBUG_LIVE_LOGGING=false
TRANSCRIPT_DEBOUNCE_SECONDS=3.0
SHORT_ANSWER_GRACE_SECONDS=2.5
```

For debugging turn-taking issues:

```env
LOG_LEVEL=DEBUG
PROCESSOR_LOG_FRAMES=true
DEBUG_LIVE_LOGGING=true
```

## Regression

Run `bash scripts/run_regression.sh` from repo root after config or processor changes.
