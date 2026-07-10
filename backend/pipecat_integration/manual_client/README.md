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
    │   └── appState.js     # Session phase constants
    ├── ui/
    │   ├── dom.js          # Central DOM id map (change layout here)
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
        └── reportClient.js       # Fetch /latest-report
```

### How to change things later

| Change | Edit |
|--------|------|
| Colors / spacing | `styles/tokens.css` |
| Conversation bubble layout | `styles/components/conversation.css` + `js/ui/conversationView.js` |
| Report sections | `js/ui/report/sections.js` (add a function per section) |
| Barge-in sensitivity | `config.js` or query params (`?barge_rms=0.06`) |
| WebSocket protocol | `js/network/voiceSession.js` |
| DOM element ids | `index.html` + `js/ui/dom.js` |

## Protocol

### Upstream (Browser → Bot)
- **Audio**: 16-bit PCM, 16 kHz mono (binary WebSocket frames)
- **Start**: `{"type":"start","target_role":"junior_ai_engineer",...}`
- **Interrupt**: `{"type":"interrupt","reason":"user_barge_in"}`

### Downstream (Bot → Browser)
- **Audio**: WAV binary chunks
- **Text**: `{"type":"text","text":"..."}`

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

## Manual verification

1. Click **Connect Mic & Bot** and allow microphone access.
2. Confirm chat bubbles appear for bot speech (and user transcripts when sent by server).
3. Speak during bot TTS to verify barge-in interruption.
4. Click **Disconnect** — report loads in the Interview Report panel.
5. Expand **Technical debug log** for PCM/WebSocket diagnostics.

## Query-string overrides

```
?ws=ws://localhost:8765
&report=http://localhost:8766/latest-report
&barge_rms=0.055
&barge_frames=4
&mic_gain=2.5
```
