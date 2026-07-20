# Pipecat WebSocket Bot — Manual Browser Client

Modular browser client for manual audio testing of the **Pipecat Voice Interview** pipeline.

## Architecture

The client is split so UI, audio, and networking can evolve independently:

```
manual_client/
├── index.html              # Page shell only (no inline styles/scripts)
├── config.js               # Runtime URLs + barge-in thresholds
├── styles/
│   ├── tokens.css          # Design tokens (colors, radii, fonts)
│   ├── base.css            # Reset + global utilities
│   ├── layout.css          # App grid + cards
│   ├── components/         # One file per UI area
│   └── main.css            # Imports all stylesheets
└── js/
    ├── app.js              # Entry point — wires modules together
    ├── core/
    │   ├── appState.js           # Session phase constants
    │   └── conversationStore.js  # Apply conversation_event → bubbles
    ├── ui/
    │   ├── dom.js          # Central DOM id map (change layout here)
    │   ├── preInterviewFlow.js  # Welcome → instructions → Ready lobby
    │   ├── statusView.js   # Connection / mic / phase indicators
    │   ├── visualizerView.js
    │   ├── conversationView.js   # Chat bubbles (bot / user / system)
    │   ├── debugLogView.js       # Collapsible technical log
    │   └── report/
    │       ├── sections.js       # Report section HTML builders
    │       └── renderReport.js   # Report orchestrator
    ├── audio/
    │   ├── bargeInController.js
    │   └── playbackController.js
    └── network/
        ├── voiceSession.js       # WebSocket + mic pipeline
        ├── inviteClient.js       # Resolve/bind recruiter invite (optional)
        └── reportClient.js       # Fetch /latest-report
```

### How to change things later

| Change | Edit |
|--------|------|
| Pre-interview lobby / copy | `js/ui/preInterviewFlow.js` + `styles/components/preInterview.css` |
| Colors / spacing | `styles/tokens.css` |
| Conversation bubble layout | `styles/components/conversation.css` + `js/ui/conversationView.js` |
| Live transcript event handling | `js/core/conversationStore.js` + `js/network/voiceSession.js` |
| Report sections | `js/ui/report/sections.js` (add a function per section) |
| Barge-in sensitivity | `config.js` or query params (`?barge_rms=0.06`) |
| Recruiter invite role | `?invite=TOKEN` (+ optional `?recruiter=http://localhost:8001`) |
| WebSocket protocol | `js/network/voiceSession.js` |
| DOM element ids | `index.html` + `js/ui/dom.js` |

## Protocol

### Upstream (Browser → Bot)
- **Audio**: 16-bit PCM, 16 kHz mono (binary WebSocket frames)
- **Start**: `{"type":"start","target_role":"junior_ai_engineer",...}`
- **Interrupt**: `{"type":"interrupt","reason":"user_barge_in"}`

### Downstream (Bot → Browser)
- **Audio**: WAV binary chunks
- **Conversation** (preferred): `{"type":"conversation_event","kind":"message","role":"assistant|user|system","text":"...","message_id":"...","status":"final",...}`
- **Phase** (optional): `{"type":"conversation_event","kind":"phase","phase":"listening|thinking|speaking"}`
- **Legacy text** (fallback): `{"type":"text","text":"..."}`

## Run

1. Start the bot:
   ```bash
   ./venv/bin/python backend/pipecat_integration/interview_bot.py
   ```

2. Serve the client (required for microphone access):
   ```bash
   ./venv/bin/python -m http.server 8000
   ```

3. Open:
   [http://localhost:8000/backend/pipecat_integration/manual_client/](http://localhost:8000/backend/pipecat_integration/manual_client/)

## Pre-interview lobby

On load, candidates see a welcome screen (**AI Interviewer** / Junior AI Engineer Interview).

1. **Start Interview** → instructions panel opens immediately (name screen goes away)  
2. Client connects and sends `{type:"instructions"}` — Cartesia speaks each line (same voice as the interview); bullets appear one-by-one  
3. **Ready** → mic permission → `{type:"start"}` on the same socket → real interview greeting  

**Important:** restart `interview_bot.py` after pulling these changes, then hard-refresh the browser (`Ctrl+Shift+R`). Do not use **Connect Mic & Bot** during the lobby — that lab button skips instructions.

Lab **Connect Mic & Bot** remains available only after the lobby closes (or for reconnect after disconnect).

## Manual verification

1. Open the client and confirm the welcome overlay (not an immediate live session).
2. Optionally fill name/resume on the welcome screen, then click **Start Interview**.
3. Confirm loading, then instruction bullets appear **one-by-one** while Cartesia speaks (same interviewer voice).
4. Wait for **Ready** to enable, click it, and confirm the real interviewer greeting in **Live Conversation**.
5. Speak an answer; after you pause, your finalized transcript should appear as a **You** bubble, then the next Interviewer question.
6. Speak during bot TTS to verify barge-in interruption.
7. Click **Disconnect**, or let the interview finish naturally — both paths show a **thank-you / completion** message (~1.5s delay). Use **Open recruiter assessment** (or `http://localhost:8766/latest-report.html`) for the detailed HTML report.
8. Expand **Technical debug log** for PCM/WebSocket diagnostics.

## Query-string overrides

```
?ws=ws://localhost:8765
&report=http://localhost:8766/latest-report
&barge_rms=0.055
&barge_frames=4
&mic_gain=2.5
```
