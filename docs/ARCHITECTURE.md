# Architecture Overview

## Runtimes

```
┌─────────────────────┐     ┌──────────────────────┐
│  interview_bot.py   │     │  main.py (FastAPI)   │
│  WS :8765 + TTS/STT │     │  REST :8000          │
└─────────┬───────────┘     └──────────┬───────────┘
          │                            │
          └──────────┬─────────────────┘
                     ▼
          ┌──────────────────────┐
          │   SessionService     │
          │   (unified sessions) │
          └──────────┬───────────┘
                     ▼
          ┌──────────────────────┐
          │  DialogueManager     │
          │  guards → eval → LLM │
          └──────────────────────┘
```

| Entry point | Role |
|-------------|------|
| `backend/pipecat_integration/interview_bot.py` | **Primary product path** — live voice |
| `main.py` | REST API, testing, optional dev text WS |
| `manual_client/` | Browser mic client for demos |

## Voice pipeline (Pipecat)

```
Browser mic → WebSocket → Deepgram STT → InterviewProcessor → Cartesia TTS → WebSocket → Browser speaker
                              │
                              └── asyncio.to_thread → InterviewDialogueAdapter → SessionService
```

**Phase 5 additions:**

- `backend/voice/voice_turn_policy.py` — debounce, echo cooldown, filler detection
- `backend/core/logging_config.py` — shared logging bootstrap
- Unified `_submit_turn()` in `interview_processor.py`

## Dialogue flow (Phases 2–4)

```
handle_turn()
  → GuardPipeline (echo, intent, incomplete, …)
  → EvaluationPipeline (primary score + optional rethink)
  → DecisionEngine
  → LLMAdapter (Groq)
  → output_sanitizer
```

Session bootstrap (Phase 3):

- `session_bootstrap.py` — optional resume, default `junior_ai_engineer` role
- `coverage_engine.py` — blueprint-driven topic coverage
- `role_registry.py` — target role definitions

## Deprecated

`dialogue/interview_flow_controller.py` — superseded by CoverageEngine + DialogueManager. Not used in Pipecat path.

## Key docs

- `docs/DIALOGUE_PIPELINE.md` — guard pipeline
- `docs/INTERVIEW_FLOW.md` — session bootstrap and coverage
- `docs/CONFIGURATION.md` — environment variables
- `docs/PERFORMANCE.md` — async and logging tuning
