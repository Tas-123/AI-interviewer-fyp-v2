# Manual Test Guide

## Prerequisites

1. Copy `.env.example` → `.env` and fill in API keys (Groq, Deepgram, Cartesia).
2. Install dependencies: `pip install -r requirements.txt -r requirements-pipecat.txt`
3. Start the Pipecat bot: `python backend/pipecat_integration/interview_bot.py`

## Browser client

1. Open `backend/pipecat_integration/manual_client/index.html` in Chrome (file:// or via report HTTP server).
2. Optionally enter display name and resume text; leave blank for default **Junior AI Engineer** profile.
3. Click **Connect Mic & Bot** — grants microphone access and opens WebSocket to `ws://localhost:8765`.
4. Speak naturally; watch the log panel for connection and barge-in events.
5. Click **Disconnect** when finished — final report loads from `http://localhost:8766/latest-report`.

## Config overrides (client)

Edit `manual_client/config.js` or pass query params:

```
index.html?ws=ws://192.168.1.10:8765&report=http://192.168.1.10:8766/latest-report
```

## REST API path (no mic)

```bash
uvicorn main:app --reload
```

- `POST /start` — optional resume, default role
- `POST /chat/{session_id}` — text turns
- `GET /report/{session_id}` — final report

## What to verify

| Check | Expected |
|-------|----------|
| First turn | Bot greeting; no startup echo scored as answer |
| Mid-interview | Follow-ups; no duplicate scoring of same utterance |
| Barge-in | Interrupt bot; clarification handled without crash |
| Short answers | Grace period allows completion before scoring |
| End | Spoken closing + report in panel / `logs/` |

## Debug logging

Set `DEBUG_LIVE_LOGGING=true` to write turn-by-turn traces to `logs/live_interview_debug.log`.

Set `LOG_LEVEL=DEBUG` and `PROCESSOR_LOG_FRAMES=true` to trace Pipecat frame flow.

## Automated smoke tests

```bash
bash scripts/run_regression.sh
```

Processor-only (no Groq):

```bash
PYTHONPATH=backend python3 backend/test_pipecat_integration.py
```

(requires project venv with dependencies installed)
