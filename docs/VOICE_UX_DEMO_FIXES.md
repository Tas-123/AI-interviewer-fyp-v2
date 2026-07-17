# Voice UX Demo Fixes

Small incremental fixes from live session `30b963f8` (no architecture rewrite).

## What changed

1. **Domain-strict questions** — Technical domains (`python`, ML, …) no longer fall back to the `role_specific` bank. Path: on-domain resume → naturalized `DOMAIN_QUESTION_SEEDS` → bounded LLM → seed.
2. **Hint path** — Phrases like “give me a hint” / “I don’t get it” route through `IdkGuard` → `hint_idk` (`Here's a small hint:`), not IntentGuard echo.
3. **Short voice questions** — Bounded domain asks: ~25-word prompt, reject multi-`?` / overlong LLM text; soft clip on commit/naturalize.
4. **STT fairness** — `apply_transcript_quality_adjustment` also triggers on `stutter_prefix`, high `reduction_ratio`, etc. (not only `is_noisy`).
5. **Groq debug logging** — With `DEBUG_LIVE_LOGGING=true`, question/eval prompts and replies append to `logs/live_interview_debug.log` (see `docs/CONFIGURATION.md`).

## Re-test

1. After intro ADVANCE to `python` → Python structure seed (not productivity behavioral).
2. “give me a hint, I don’t get it” → hear hint + short re-ask.
3. Primary domain questions stay roughly one spoken sentence.
4. `DEBUG_LIVE_LOGGING=true` → log shows `GROQ_*_PROMPT` / `GROQ_*_REPLY`.
5. Stuttery turns get fairness reweight more often.
