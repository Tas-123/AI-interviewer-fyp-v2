# Configuration Reference

All settings load from environment variables (`.env` at repo root). See `.env.example` for defaults.

## LLM (Groq)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | *(required)* | API key for question generation and evaluation |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Primary model for `LLMAdapter` (interview questions) |
| `GROQ_EVALUATOR_MODEL` | falls back to `GROQ_MODEL` | Model for `Evaluator` scoring and rethink |

## Voice turn timing (Pipecat `InterviewProcessor`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `TRANSCRIPT_DEBOUNCE_SECONDS` | `3.0` | Wait after VAD stop before finalizing utterance |
| `SHORT_ANSWER_GRACE_SECONDS` | `2.5` | Extra wait when transcript ≤ word threshold |
| `SHORT_ANSWER_WORD_THRESHOLD` | `6` | Word count that triggers grace period |
| `STARTUP_AUDIO_GATE_SECONDS` | `4.0` | Ignore mic input during intro startup |
| `STARTUP_REFRESH_SECONDS` | `3.0` | Extend startup gate while bot speaks first question |
| `BOT_ECHO_COOLDOWN_SECONDS` | `1.2` | Ignore mic while/after bot TTS (echo suppression) |
| `BOT_STOP_ECHO_COOLDOWN_SECONDS` | `0.8` | Cooldown after bot stops speaking |
| `CLOSING_DELAY_SECONDS` | `2.5` | Pause before `EndTaskFrame` after closing line |
| `FINAL_TRANSCRIPT_DEBOUNCE_SECONDS` | `0.35` | Debounce after final STT before turn submit |
| `TURN_RESUME_WINDOW_SECONDS` | `0.75` | After submit, window to absorb/suppress STT tail fragments |
| `TURN_TAIL_MAX_WORDS` | `6` | Max words treated as a suspicious post-answer tail |
| `TURN_TAIL_MIN_WORDS_FOR_SUSPICION` | `10` | Prior answer length before tail suppression applies |

See also: `docs/VOICE_TAIL_FRAGMENT_FIX.md` for July 15/16 tail-fragment QA details.

Policy object: `backend/voice/voice_turn_policy.py` — loaded via `VoiceTurnPolicy.from_settings(settings)`.

## Logging

| Variable | Default | Purpose |
|----------|---------|---------|
| `LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, …) |
| `PROCESSOR_LOG_FRAMES` | `false` | Log every Pipecat frame type (verbose; demo debugging only) |
| `DEBUG_LIVE_LOGGING` | `false` | Append human-readable turn traces to `logs/live_interview_debug.log` |

Bootstrap: `backend/core/logging_config.py` — called from `main.py` and `interview_bot.py`.

## Pipecat / HTTP

| Variable | Default | Purpose |
|----------|---------|---------|
| `PIPECAT_WS_HOST` | `localhost` | WebSocket bind host |
| `PIPECAT_WS_PORT` | `8765` | Voice WebSocket port |
| `REPORT_HTTP_PORT` | `8766` | Manual client report HTTP server |

## Manual browser client

`backend/pipecat_integration/manual_client/config.js` centralizes URLs and barge-in thresholds.

Query-string overrides:

- `?ws=ws://host:8765`
- `?report=http://host:8766/latest-report`
- `?barge_rms=0.035&barge_frames=3`

## Database

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | *(optional)* | PostgreSQL connection string; in-memory fallback if unset |

## Development flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_DEV_TEXT_VOICE_WS` | `false` | FastAPI text WebSocket simulation (not product voice path) |
