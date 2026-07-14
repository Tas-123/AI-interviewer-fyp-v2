# Voice Turn-Taking Fixes — Premature Turns, Barge-In Speech Loss, Report UX

**Date:** 2026-07-14  
**Branch:** `uthman`  
**Status:** Implemented + regression green  
**Scope:** Voice turn-boundary / UX only — no scoring or LLM dialogue logic changes

---

## Why this push

Manual interview logs showed the LLM was usually fine. Failures came from turn-boundary logic: interim silence fallback submitting too early, echo cooldown wiping real speech after barge-in, junk check-ins becoming full turns, over-aggressive early `AUDIO_ISSUE` guards, and the report UI only loading after a manual Disconnect click.

---

## Problems Fixed

| # | Symptom | Root cause |
|---|---------|------------|
| 1 | Bot cuts off mid-intro (e.g. submits `"Yeah. So"`) | Interim silence fallback treated short partials as finished turns |
| 2 | Real answer after interrupt disappears | Echo cooldown cleared transcript buffer during post–barge-in speech |
| 3 | `"hello?"` / `"hear me?"` after micro-interrupt derails interview | Short/check-in transcripts went to dialogue + intent redirects |
| 4 | Early mic-check burns turns on AUDIO_ISSUE redirects | Intent guard treated early check-ins like hard failures |
| 5 | Report missing unless user clicks Disconnect | Client only loaded report from the Disconnect button path |
| 6 | Long mid-answer pauses split into multiple turns | Silero `stop_secs` too aggressive (`0.55`) → SPEAKING↔STOPPING flap |

---

## Changes Made

### 1. Gate interim silence fallback — `interview_processor.py`

- Do **not** finalize from interim silence fallback while VAD still indicates speaking.
- Require recent final STT **or** a quiet/stopped VAD state before falling back.
- Raise minimum buffered words (≈8–12) so fragments never become turns.
- Prefer VAD stop + final STT debounce (~0.35s); keep interim fallback as last resort only.

### 2. Preserve speech after barge-in — `interview_processor.py`

- On successful barge-in, set a short **mic-allow window** (`_barge_in_mic_allow_until`).
- During that window, echo discard **does not clear** the transcript buffer.
- Shorten post-interrupt echo cooldown while barge-in is active (~0.25s vs ~0.8s).

### 3. Reject junk post–barge-in turns — `interview_processor.py`

- `_is_check_in_or_junk()` detects short / check-in phrases (`hello?`, `hear me?`, etc.).
- During barge-in allow window, short or junk transcripts are discarded quietly (no AUDIO_ISSUE redirect).

### 4. Soften early intent guards — `intent_guard.py`

- For first ~2 evaluated turns (`turn_count <= 2`):
  - Short `AUDIO_ISSUE` / `CLARIFICATION_REQUEST` check-ins are **non-blocking** (`triggered=False`).
- Normal intent handling remains after the interview is underway.

### 5. Auto-load report on natural end — manual client

- `voiceSession.js`: `createVoiceSession(config, ui, hooks)` with `onSessionEnded`.
- Called from natural `{"type":"end"}` handling and disconnect / `ws.onclose`.
- `app.js`: schedules `loadReport(ui)` after ~1.5s (server persists report on disconnect); debounced to avoid double-load.
- Disconnect button behavior preserved; README notes both paths load the report.

### 6. VAD stability — `interview_bot.py`

- Raised Silero `stop_secs`: `0.55 → 0.80` to reduce flapping on thinking pauses.

### 7. Tests

- New: `backend/tests/test_voice_turn_taking_fixes.py`
  - Interim fallback does not submit short partials without VAD stop/final
  - Barge-in mic-allow bypasses echo buffer clear
  - Post–barge-in short/check-in transcripts rejected
  - Early AUDIO_ISSUE check-ins do not hard-redirect
- Wired into `scripts/run_regression.sh`
- Full regression suite: **all checks passed**

---

## Files Touched

| File | Change |
|------|--------|
| `backend/pipecat_integration/interview_processor.py` | Interim gate, mic-allow, junk reject, echo bypass |
| `backend/dialogue/guards/intent_guard.py` | Soft early AUDIO_ISSUE / clarification |
| `backend/pipecat_integration/interview_bot.py` | `stop_secs=0.80` |
| `backend/pipecat_integration/manual_client/js/network/voiceSession.js` | `onSessionEnded` hook |
| `backend/pipecat_integration/manual_client/js/app.js` | Auto report load on end/close |
| `backend/pipecat_integration/manual_client/README.md` | Document auto report paths |
| `backend/tests/test_voice_turn_taking_fixes.py` | New unit tests |
| `scripts/run_regression.sh` | Include new test |
| `docs/VOICE_TURN_TAKING_FIXES.md` | This push doc |

---

## Out of Scope (this push)

- Session-scoped report HTTP API redesign
- Resume pipeline activation / e2e resume tests
- Scoring / rubric changes
- PDF export

---

## How to Verify Manually

1. Restart bot + hard-refresh manual client.
2. **Long intro:** speak 20–40s without cut-off mid-sentence.
3. **Barge-in:** interrupt mid-question, keep talking — answer should reach dialogue (not wiped).
4. **Junk check-in:** after a micro-interrupt, say `"hello?"` — should not derail into AUDIO_ISSUE storm.
5. **Early mic check:** early `"can you hear me?"` should not burn a hard redirect turn.
6. **Report:** finish naturally (or disconnect) — report panel fills without needing an extra click beyond session end.

### Automation

```bash
PATH="$(pwd)/venv/bin:$PATH" PYTHONPATH=backend bash scripts/run_regression.sh
```
