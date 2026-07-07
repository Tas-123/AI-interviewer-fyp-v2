# Phase 6 Voice Hotfix — Reconnect & STT Capture

**Date:** 2026-07-07  
**Status:** Applied locally (post `534b860` push)  
**Scope:** Pipecat voice pipeline only — no dialogue/evaluation logic changes

---

## Problems Fixed

| # | Symptom | Root cause |
|---|---------|------------|
| 1 | Reconnect after disconnect = silent bot | Client sent `{"type":"end"}` → `EndFrame` tore down Deepgram/Cartesia |
| 2 | Greeting plays, user speaks, bot never responds | Silero VAD never detected speech → Deepgram never finalized → no transcript reached dialogue |
| 3 | “240 audio chunks loop” | Misread — one greeting streamed as many small WAV chunks (not a bug) |

---

## Changes Made

### 1. `backend/pipecat_integration/manual_client/client.js`

- **Removed** `ws.send({type:"end"})` on disconnect — closing the WebSocket is enough.
- **Mic routing:** ScriptProcessor → silent gain node (gain=0) → destination (prevents speaker echo weakening STT).
- **Mic gain boost:** `MIC_GAIN=2.5` applied before PCM conversion (configurable).
- **Logging:** Per-second RMS + gain in audio stream logs for debugging.

### 2. `backend/pipecat_integration/manual_client/config.js`

- Added `micGain` (default `2.5`, override via `?mic_gain=3`).

### 3. `backend/pipecat_integration/interview_bot.py`

- **Ignore client `type:end`** — do not inject `EndFrame` (prevents STT/TTS teardown on reconnect).
- **VAD tuning:** `confidence=0.30`, `min_volume=0.015`, `start_secs=0.12`, `stop_secs=0.40`.
- **VADProcessor:** `audio_idle_timeout=2.0` to force speech-end when VAD stalls.
- **`reset_for_new_session()`** called on each new WebSocket connect.

### 4. `backend/pipecat_integration/interview_processor.py`

- **`reset_for_new_session()`** — clears buffers, debounce tasks, barge-in state per connection.
- **Unified STT path:** all final `TranscriptionFrame` events schedule debounced turn processing (no longer gated on `vad_enabled`).
- **Interim STT fallback:** after interim text + 1.4s silence, schedule turn even if VAD missed speech.
- **INFO logging:** `Buffered interim STT`, `Final STT transcript received`, `Interim STT silence fallback`.

### 5. `backend/test_pipecat_integration.py`

- Test processor uses zero debounce; awaits pending async tasks after `process_frame`.

---

## Voice Pipeline (After Fix)

```
Browser mic (+ gain) → WebSocket PCM
  → VAD (sensitive thresholds)
  → Deepgram STT (interim + final)
  → InterviewProcessor
       ├─ VAD stop → debounce → dialogue
       ├─ Final STT → debounce → dialogue   [NEW: always]
       └─ Interim + silence → debounce     [NEW: fallback]
  → DialogueManager.handle_turn()
  → Cartesia TTS → client audio
```

---

## How to Test

1. Kill old bot: `fuser -k 8765/tcp`
2. Start bot: `.venv/bin/python backend/pipecat_integration/interview_bot.py`
3. Serve client: `python -m http.server 8888` from project root
4. Hard refresh: `http://localhost:8888/backend/pipecat_integration/manual_client/`
5. Connect → wait for greeting → speak 3–5s → pause → expect follow-up within ~5s
6. Disconnect → reconnect without refresh → greeting should play again

### Log lines to confirm fix

**Server (bot terminal):**
- `Final STT transcript received: '...'`
- `Processing user transcript: '...'`
- No `Disconnecting from Deepgram` on normal client disconnect

**Client:**
- `RMS=0.0xxx gain=2.5` (RMS should rise when speaking)
- `Received bot audio chunk` after you answer

---

## Not Changed

- Phase 6A–6C dialogue flow, guards, transcript quality, reporting (`534b860`)
- Deepgram API key / Cartesia configuration (except existing Phase 6B settings)

---

## Related Commits

- `534b860` — Phase 6A–6C (pushed)
- `379744c` — Voice reconnect + STT capture hotfix (pushed)
- Interview flow fixes — skip intent, redirect dedup, transcript merge (see below)

---

## Interview Flow Fixes (post live test `2e2c4388`)

**Date:** 2026-07-07  
**Session analyzed:** `2e2c4388-44e2-4354-a3ca-27f61d8d749b`

| # | Symptom | Fix |
|---|---------|-----|
| 1 | "Move to next question" blocked as OFF_TOPIC | `SKIP_REQUEST` intent + meta guard phrases → `skip_domain` |
| 2 | Redirect text stacked in TTS (triple-nested prompts) | `canonical_interview_question()` strips guard prefixes |
| 3 | Interim STT merge produced 60–70% repeated tokens | Progressive phrase collapse + smarter `_merge_transcript_part` |
| 4 | High-repetition transcripts not flagged noisy | Lower `is_noisy` threshold when `repeated_token_ratio >= 0.50` |
| 5 | VAD split one answer into many fragments | `stop_secs` 0.40 → 0.55 |
| 6 | Client barge-in did not stop server TTS promptly | `request_client_interrupt()` on `{"type":"interrupt"}` |

**Files:** `intent_guard.py`, `meta_conversation_guard.py`, `domain_guard.py`, `echo_guard.py`, `idk_policy.py`, `transcript_utils.py`, `transcript_quality.py`, `interview_processor.py`, `interview_bot.py`

**Tests:** `backend/tests/test_guards/test_interview_flow_fixes.py`
