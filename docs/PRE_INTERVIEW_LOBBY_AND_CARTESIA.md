# Pre-Interview Lobby + Cartesia Instructions

**Date:** 2026-07-18  
**Branch:** `uthman`  
**Status:** Implemented  

---

## Why this update

The manual client used to jump straight into **Connect Mic & Bot** / live interview. That felt like a lab console, not a candidate product. We added a lightweight **pre-interview lobby** on the existing frontend only (no recruiter portal / SaaS wrapper), then upgraded instruction speech to use the **same Cartesia voice** as the live interviewer, with text appearing **line-by-line**.

---

## What we built

### 1. Frontend pre-interview lobby (manual client only)

Flow:

1. **Welcome** — brand **AI Interviewer**, title *Junior AI Engineer Interview*, optional name/resume, **Start Interview**
2. **Instructions** — panel opens immediately after Start; bullets appear as they are spoken
3. **Ready** — mic permission (if needed) → real interview starts on the same WebSocket

Intentionally unchanged:

- DialogueManager, guards, evaluation, STT, rubric, Report v2
- Coverage / skip / domain stickiness policy

### 2. Same interviewer voice (Cartesia)

Browser `speechSynthesis` was removed for instructions (it used a different system voice, often male).

Instead:

- Client connects and sends `{type:"instructions"}` (does **not** start the interview)
- Server speaks fixed lines via existing `TTSSpeakFrame` → **Cartesia** (`CARTESIA_VOICE_ID`)
- Client later sends `{type:"start"}` on **Ready** → existing `begin_interview` + greeting path

Copy lives in one place: [`backend/pipecat_integration/preamble_copy.py`](../backend/pipecat_integration/preamble_copy.py).

### 3. Incremental on-screen instructions

For each preamble line the server:

1. Emits a `conversation_event` message (assistant)
2. Speaks that line with Cartesia
3. Waits for `BotStoppedSpeakingFrame`
4. Continues to the next line

After the last line it emits `session` action `instructions_complete`, which enables **Ready**.

The UI starts with an empty list and **appends one `<li>` per spoken line** (not a full dump up front).

---

## Handshake change (important)

| Message | Meaning |
|---------|---------|
| WebSocket connect | Prepare processor only — **do not** auto-start dialogue |
| `{type:"instructions"}` | Cartesia preamble only |
| `{type:"start", ...}` | `adapter.start_interview(...)` + greeting TTS (same as before) |

`on_client_connected` no longer starts the interview by itself. Interview begins only on explicit `start`.

During preamble, `InterviewProcessor` ignores STT turns (`preamble_active` / `interview_live` gates).

---

## Files touched

| File | Role |
|------|------|
| `backend/pipecat_integration/preamble_copy.py` | Instruction line list |
| `backend/pipecat_integration/interview_bot.py` | `instructions` / `start` handlers; deferred auto-start |
| `backend/pipecat_integration/interview_processor.py` | Bot-stop waiters; ignore STT during preamble |
| `manual_client/index.html` | Welcome / instructions / Ready overlay |
| `manual_client/js/ui/preInterviewFlow.js` | Lobby state machine |
| `manual_client/js/network/voiceSession.js` | `connect` / `sendInstructions` / `sendStart` / `ensureMicrophone` |
| `manual_client/js/app.js` | Wire Start → instructions; Ready → start |
| `manual_client/js/ui/dom.js` | Overlay DOM refs |
| `manual_client/styles/components/preInterview.css` | Lobby styling |
| `manual_client/README.md` | Operator notes |

---

## Live QA fixes (same push)

| Symptom | Cause | Fix |
|---------|--------|-----|
| Start kept the name screen / felt like interview jumped early | Mic permission + connect ran before leaving welcome; failures bounced back to welcome | Switch to **instructions panel immediately** on Start; never return to welcome on connect error |
| Interview greeting during lobby + `sendInstructions is not a function` | Stale cached `voiceSession.js` (old `connect` sent `start` on open; new `app.js` called missing `sendInstructions`) | Ensure modules export `sendInstructions`; hard-refresh client; restart bot |
| Lab **Connect Mic & Bot** skipped lobby | Still wired to `connectAndStart()` | Hidden during `pre-interview-active`; mic deferred until Ready |

---

## How to run / re-test

1. Restart the voice bot (required after handshake change):

```bash
python backend/pipecat_integration/interview_bot.py
```

2. Serve the client and **hard-refresh** (`Ctrl+Shift+R`):

```bash
cd backend/pipecat_integration/manual_client
python -m http.server 3000
```

3. Checklist:

- [ ] Welcome overlay shows first (not the lab shell)
- [ ] **Start Interview** → instructions panel (name screen gone)
- [ ] Cartesia speaks instructions (same voice as later greeting)
- [ ] Bullets appear one-by-one
- [ ] **Ready** enables after `instructions_complete`
- [ ] Ready → mic (if needed) → real intro greeting
- [ ] Do **not** use **Connect Mic & Bot** during the lobby

---

## Out of scope (still)

- Recruiter portal / unique interview links / auth
- Video interview type
- Dialogue / evaluation / STT pipeline redesign
- Changing `CARTESIA_VOICE_ID` itself
