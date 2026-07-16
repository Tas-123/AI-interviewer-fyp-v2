# AI-Based Real-Time Interview Simulator with Adaptive Questioning and Automated Evaluation

**Final Year Project Technical Report — Version 2.0**

---

| Field | Detail |
|-------|--------|
| **Project Title** | AI-Based Real-Time Interview Simulator with Adaptive Questioning and Emotion Analysis *(proposal title; emotion analysis deferred — see §12)* |
| **Institution** | Hamdard University Islamabad |
| **Supervisor** | Engineer Usman Javed |
| **Team** | Muhammad Usman, Taimur Ali Sakhawat, Bismah Khan Bangash, Eimaan Khan Bangash |
| **Academic Year** | 2025–2026 |
| **Repository** | `AI-interviewer-fyp-v2` |
| **Authoritative branch** | `uthman` |
| **Implementation snapshot** | Commit `64a7d784` (2026-07-16) — *Add recent Q&A memory to question prompts for interview continuity* |
| **Primary LLM** | Groq (`llama-3.3-70b-versatile`) |
| **STT / TTS / Voice** | Deepgram nova-2 · Cartesia · Pipecat + Silero VAD |
| **Supersedes** | `docs/FYP_FINAL_REPORT.md` (v1.0, frozen at commit `852bf7e`) |

> **Authority note.** This document is the **current** FYP technical report. It was rebuilt from the live codebase, Git history on `uthman`, and post-Phase-6 documentation (`FULL_COVERAGE_INTERVIEW.md`, `VOICE_*`, `WIRE_LIVE_CONVERSATION.md`, `FYP_MEMORY_CONTINUITY.md`, phase completion reports, `dev_file.md`, etc.). The older `FYP_FINAL_REPORT.md` remains historical reference only.

---

## Table of Contents

1. [Project Overview and Objectives](#1-project-overview-and-objectives)
2. [Problem Statement](#2-problem-statement)
3. [Current Architecture](#3-current-architecture)
4. [System Design](#4-system-design)
5. [Complete Project Structure](#5-complete-project-structure)
6. [Technology Stack and Libraries](#6-technology-stack-and-libraries)
7. [Core Modules and Responsibilities](#7-core-modules-and-responsibilities)
8. [End-to-End Interview Workflow](#8-end-to-end-interview-workflow)
9. [AI Pipeline](#9-ai-pipeline)
10. [Backend Architecture and Service Interactions](#10-backend-architecture-and-service-interactions)
11. [Database and Storage](#11-database-and-storage)
12. [APIs and Communication Flow](#12-apis-and-communication-flow)
13. [Configuration and Deployment](#13-configuration-and-deployment)
14. [Features Implemented Phase by Phase](#14-features-implemented-phase-by-phase)
15. [Major Architectural Decisions](#15-major-architectural-decisions)
16. [Improvements Since the Original Proposal](#16-improvements-since-the-original-proposal)
17. [Challenges Encountered and Resolutions](#17-challenges-encountered-and-resolutions)
18. [Current Implementation Status](#18-current-implementation-status)
19. [Remaining Work](#19-remaining-work)
20. [Conclusion](#20-conclusion)
21. [Appendix A — Git Evolution Timeline](#appendix-a--git-evolution-timeline)
22. [Appendix B — Documentation Index](#appendix-b--documentation-index)

---

## 1. Project Overview and Objectives

### 1.1 Overview

This Final Year Project delivers a **real-time AI voice interviewer** for Junior AI Engineer candidates. A candidate speaks into a browser microphone; the system transcribes speech, manages a structured multi-domain interview, evaluates answers with a transparent LLM rubric, asks adaptive follow-ups, and produces a recruiter-facing report (JSON + HTML).

The product demo path is a **Pipecat** WebSocket voice server. A **FastAPI** REST layer supports text-based testing and report retrieval. A modular **vanilla HTML/JS** manual client provides the live UI.

### 1.2 Objectives — Status Against Delivery

| ID | Objective | Status (as of `64a7d784`) |
|----|-----------|---------------------------|
| O1 | Real-time voice interview simulation | **Achieved** — Pipecat + Deepgram + Cartesia + Silero |
| O2 | Dynamic adaptive questioning | **Achieved** — CoverageEngine + DecisionEngine + Groq adaptive evaluate |
| O3 | Interruption (barge-in) handling | **Achieved with limits** — client RMS + server VAD grace; not ASR-gated |
| O4 | Emotional & behavioural evaluation | **Partially achieved** — six-dimension LLM rubric from text (clarity/confidence as proxies); **no SER/facial models** |
| O5 | Automated interview reporting | **Achieved** — Report v2 (`backend/reporting/`), completion tiers, HTML export |
| O6 | Reliability & evaluation methodology | **Achieved** — phased regression suite, noisy-STT fairness, human-study export API |

### 1.3 Scope of the Delivered System

**In scope (implemented):**

- Live browser voice interview (primary)
- Optional resume personalisation and default Junior AI profile
- Ten-domain Junior AI Engineer blueprint with coverage-first wrap-up
- Six-guard pre-evaluation pipeline
- Adaptive PROBE / ADVANCE decisions with question deduplication
- Six-dimension weighted rubric + borderline rethink ensemble
- Transcript quality assessment and noisy-STT score reweighting
- Recent Q&A continuity in question (and light evaluator) prompts
- Live conversation events in the browser UI
- Report v2 with complete / partial / incomplete / aborted tiers
- Optional PostgreSQL persistence; in-memory fallback
- Human-study CSV/JSON export endpoint for κ validation

**Out of scope (not implemented):**

- Speech Emotion Recognition and facial expression analysis
- Full IRT / CAT psychometric engine
- React/Firebase frontend and Docker/cloud deployment
- Multi-worker / multi-tenant concurrent voice sessions
- Vector memory, Redis, or RAG-based recall

---

## 2. Problem Statement

Candidates preparing for AI engineering roles lack accessible, realistic, repeatable interview practice. Existing tools often provide static question banks, text-only chatbots, or generic HR screens without domain-specific adaptive probing.

Automated voice interview systems frequently fail on:

1. **Latency and streaming** — acceptable STT → decision → TTS loops
2. **Turn-taking** — barge-in, silence, premature finalisation, STT tail fragments
3. **Non-answers** — echoes, meta-requests (“repeat”), IDK, off-topic speech scored as content
4. **Fairness** — communication scores punished by ASR noise rather than candidate ability
5. **Honesty in reporting** — interviews marked “complete” after covering only part of a skill blueprint

This project addresses those failures with a guarded dialogue pipeline, coverage-first interview policy, transcript-fair evaluation, and tiered reporting — delivered as a demonstrable end-to-end voice system suitable for academic evaluation.

---

## 3. Current Architecture

### 3.1 Runtime Faces, One Brain

```
┌────────────────────────────┐     ┌─────────────────────────┐
│  interview_bot.py          │     │  main.py (FastAPI)      │
│  WS :8765 + report HTTP    │     │  REST :8000             │
│  :8766                     │     │  (optional text WS)     │
└─────────────┬──────────────┘     └────────────┬────────────┘
              │                                 │
              └──────────────┬──────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │   SessionService     │
                  │   (in-process store) │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │  DialogueManager     │
                  │  guards → eval →     │
                  │  decide → generate   │
                  └──────────────────────┘
```

| Entry point | Role |
|-------------|------|
| `backend/pipecat_integration/interview_bot.py` | **Primary product path** — live voice |
| `main.py` | REST API, testing, optional dev text WebSocket |
| `backend/pipecat_integration/manual_client/` | Browser mic client + live transcript + report UI |

Sessions share one `SessionService` **only within the same Python process**. Running the bot and FastAPI as separate processes yields separate session stores.

### 3.2 Voice Pipeline (Primary)

```
Browser mic (PCM over WebSocket)
  → Deepgram STT (interim + final frames)
  → InterviewProcessor
       • merge / debounce / echo gate / barge-in / silence / tail suppress
       • ConversationEventPublisher (UI bubbles + phase)
  → asyncio.to_thread(InterviewDialogueAdapter.process_user_text)
  → SessionService → DialogueManager.handle_turn
  → Cartesia TTS (TTSSpeakFrame)
  → WebSocket audio + conversation_event JSON → browser
  → on end: reporting.persistence → reports/*.json + HTML
```

### 3.3 Dialogue Pipeline (Every Scored Turn)

```
prepare_transcript_for_evaluation()
  → GuardPipeline (first trigger wins):
       Echo → Meta → IDK → Intent → Incomplete → Domain
  → Evaluator.adaptive_evaluate()
       → EvaluationPipeline (primary + optional rethink)
       → optional noisy-STT weight adjustment
  → DecisionEngine.decide_from_adaptive()
       → CoverageEngine (domain progression, skip budget, wrap rules)
  → LLMAdapter.generate() when intro / advance needs a new question
       → recent Q&A memory + sliding question history
  → question_dedup + output_sanitizer
  → InterviewContext update (+ optional Postgres save)
```

### 3.4 Context / Memory Model

The system does **not** replay a full chat `messages[]` history to Groq.

- Live state lives in **`InterviewContext`** (in-process via `SessionService`).
- Each Groq call is typically a **fresh system + constructed user prompt**.
- As of commit `64a7d784`, the last **three** answer-aware Q&A pairs are injected into technical / behavioural / follow-up prompts (and lightly into adaptive evaluation), with soft character caps.
- Question history shown to the LLM is a **sliding window of the last six questions**.
- PostgreSQL stores sessions/responses for reports and recovery metadata; it is **not** read back into LLM prompts at runtime.

---

## 4. System Design

### 4.1 Interview Blueprint (Junior AI Engineer)

Fixed domain order (practical Q-matrix; not IRT/CAT):

1. `project_overview`
2. `python`
3. `machine_learning`
4. `data_preprocessing`
5. `model_evaluation`
6. `nlp_speech_ai`
7. `apis_backend`
8. `deployment`
9. `debugging_problem_solving`
10. `behavioral_ownership`

**Policy constants** (`backend/core/interviewer_policy.py`):

| Constant | Value | Meaning |
|----------|-------|---------|
| `MAX_TURNS_PER_DOMAIN` | 1 | One primary question per domain |
| `MAX_PROBES_PER_DOMAIN` | 1 | One probe follow-up per domain |
| `MAX_TOTAL_INTERVIEW_TURNS` | **28** | Safety ceiling only |
| `MAX_SKIPS_PER_INTERVIEW` | **2** | Hard skip budget |
| `MAX_CONTEXT_FOLLOWUPS_TOTAL` | 3 | Context follow-up budget |

**Coverage-first wrap-up** (July 2026): the interview does **not** close solely because turn count hit a low cap. Wrap-up prefers **full blueprint coverage**; the 28-turn limit is a safety ceiling. Soft phrases like “next question” **stay on the current question**; hard skips consume budget.

### 4.2 Interviewer Persona

The system **asks, evaluates, and redirects**. It does not coach or provide sample answers. Persona rules and coaching blocklists live in `interviewer_policy.py` and are enforced in prompts and `output_sanitizer`.

### 4.3 Session Bootstrap

Optional `resume_text` / `resume_data` / `display_name` / `target_role` flow through `session_bootstrap.py` into a `CandidateProfile`. Default role: `junior_ai_engineer`. Missing resume → `DEFAULT_CANDIDATE_PROFILE`.

### 4.4 Evaluation Design

- **Method name:** `llm_rubric_ensemble_lite_v1`
- **Rubric version:** `1.0`
- **Six dimensions** with weights summing to 1.0 (see §9.5)
- **Borderline rethink:** second Groq pass when weighted score ∈ [2.2, 3.5] or dimension spread ≥ 1.5
- **Noisy STT:** alternate weights reduce communication impact when transcript quality is poor
- **Profiles:** communication vs technical composites for reporting (Phase 6C)

### 4.5 Report v2 Design

`backend/reporting/` wraps legacy analytics into versioned reports:

- `report_version = "2.0"`
- Types: `complete` | `partial` | `incomplete` | `aborted`
- **Complete** requires wrap-up state, ≥5 evaluated turns, and **100%** blueprint coverage visited
- HTML renderer + disk persistence; aborted sessions isolated under `reports/aborted/`
- Legacy top-level analytics keys mirrored for existing consumers

---

## 5. Complete Project Structure

```text
AI-interviewer-fyp-v2/
├── main.py                          # FastAPI REST entry (v5.0.0)
├── requirements.txt                 # Core: FastAPI, Groq, Postgres driver, …
├── requirements-pipecat.txt         # Pipecat + Deepgram + Cartesia + Silero
├── pytest.ini
├── .env.example
├── README.md
├── scripts/
│   └── run_regression.sh            # Official Phase 3–6+ regression runner
├── docs/                            # Architecture, phase reports, QA notes
├── logs/                            # Runtime / live debug logs
├── reports/                         # Generated JSON/HTML (incl. aborted/)
└── backend/
    ├── core/
    │   ├── config.py                # Settings from .env
    │   ├── session_service.py       # Unified session singleton
    │   ├── role_registry.py         # target_role → blueprint
    │   ├── interviewer_policy.py    # Blueprint, limits, persona, spoken copy
    │   └── logging_config.py
    ├── dialogue/
    │   ├── dialogue_manager.py      # Turn orchestrator
    │   ├── context.py               # InterviewContext + recent Q&A helpers
    │   ├── coverage_engine.py
    │   ├── decision_engine.py
    │   ├── llm_adapter.py
    │   ├── evaluator.py
    │   ├── evaluation_pipeline.py
    │   ├── prompts.py
    │   ├── session_bootstrap.py
    │   ├── question_selector.py / question_bank.json
    │   ├── question_dedup.py
    │   ├── transcript_utils.py / transcript_quality.py
    │   ├── followup_policy.py / output_sanitizer.py / idk_policy.py
    │   ├── analytics.py / recruiter_report.py / database.py
    │   ├── interview_flow_controller.py   # DEPRECATED
    │   └── guards/
    │       ├── pipeline.py
    │       ├── echo_guard.py
    │       ├── meta_conversation_guard.py
    │       ├── idk_guard.py
    │       ├── intent_guard.py
    │       ├── incomplete_guard.py
    │       ├── domain_guard.py
    │       ├── relevance.py
    │       └── types.py
    ├── evaluation/
    │   ├── rubric.py
    │   └── human_study_export.py
    ├── integration/
    │   └── dialogue_adapter.py      # Pipecat ↔ SessionService facade
    ├── pipecat_integration/
    │   ├── interview_bot.py
    │   ├── interview_processor.py
    │   ├── config.py
    │   ├── conversation/
    │   │   ├── events.py
    │   │   └── publisher.py
    │   └── manual_client/           # Modular browser demo
    │       ├── index.html / config.js / client.js
    │       ├── js/                  # app, audio, core, network, ui
    │       └── styles/
    ├── reporting/                   # Report v2
    │   ├── generator.py / builders.py / completion_policy.py
    │   ├── narrative.py / naming.py / persistence.py / schema.py
    │   └── renderers/html_renderer.py
    ├── voice/
    │   ├── voice_turn_policy.py     # Debounce, silence, barge timing
    │   ├── websocket_router.py      # Dev text WS (optional)
    │   └── …                        # Dev-only orchestrator helpers
    └── tests/                       # Official pytest / smoke suites
```

Workspace note: the Git root is `AI-interviewer-fyp-v2/`. Parent folder `application_v01/` may hold a local `venv/` and is not the repository root.

---

## 6. Technology Stack and Libraries

| Layer | Technology |
|-------|------------|
| Language | Python 3.12 |
| REST | FastAPI + Uvicorn + Pydantic |
| Voice framework | Pipecat (`pipecat-ai[deepgram,cartesia,websocket,silero]`) |
| STT | Deepgram (`nova-2`) |
| TTS | Cartesia |
| VAD | Silero (via Pipecat) |
| LLM | Groq API — Llama 3.3 70B (default); optional separate evaluator model |
| Database | Optional PostgreSQL via `psycopg2-binary` |
| Frontend demo | Vanilla HTML / CSS / JS (modular) |
| Config | `python-dotenv` + `core.config.Settings` |
| Testing | pytest harness + `scripts/run_regression.sh` |

**`requirements.txt`:** `fastapi`, `uvicorn`, `python-dotenv`, `psycopg2-binary`, `websockets`, `groq`  
**`requirements-pipecat.txt`:** `pipecat-ai[deepgram,cartesia,websocket,silero]`

There is **no** Dockerfile, docker-compose, Kubernetes, or CI config in this repository. Deployment is local Python + `.env`.

---

## 7. Core Modules and Responsibilities

### 7.1 `backend/core/`

| Module | Responsibility |
|--------|----------------|
| `config.py` | Typed `Settings` — single source for API keys and voice timing |
| `session_service.py` | Process-wide session create / turn / end / report |
| `role_registry.py` | Maps `junior_ai_engineer` → blueprint + defaults |
| `interviewer_policy.py` | Blueprint, turn/skip limits, persona, closing TTS copy |
| `logging_config.py` | Shared logging bootstrap |

### 7.2 `backend/dialogue/`

| Module | Responsibility |
|--------|----------------|
| `dialogue_manager.py` | End-to-end `handle_turn` orchestration |
| `context.py` | Per-session state, coverage hooks, recent Q&A formatting |
| `coverage_engine.py` | Domain visit / probe / advance / skip accounting |
| `decision_engine.py` | Intro / probe / advance / closing decisions |
| `llm_adapter.py` | Groq question generation (intro, technical, behavioural, follow-up) |
| `evaluator.py` | Adaptive evaluate (score + next-step suggestion) |
| `evaluation_pipeline.py` | Primary + rethink merge |
| `prompts.py` | All long-form LLM prompt templates |
| `session_bootstrap.py` | Normalize start payloads → `CandidateProfile` |
| `guards/*` | Pre-evaluation short-circuit filters |
| `transcript_*` | STT cleanup, merge, quality scoring |
| `analytics.py` | Pure-function report analytics (legacy core) |
| `recruiter_report.py` | HR summaries and ranking helpers |
| `database.py` | Optional Postgres persistence |
| `interview_flow_controller.py` | **Deprecated** — superseded by CoverageEngine |

### 7.3 Integration, Voice Product, Reporting

| Module | Responsibility |
|--------|----------------|
| `integration/dialogue_adapter.py` | Stable `start_interview` / `process_user_text` / `end_interview` API |
| `pipecat_integration/interview_bot.py` | Assemble pipeline, WS server, report HTTP |
| `pipecat_integration/interview_processor.py` | FrameProcessor bridge STT ↔ dialogue ↔ TTS |
| `pipecat_integration/conversation/*` | Versioned live UI events |
| `voice/voice_turn_policy.py` | Config-driven timing policy object |
| `reporting/*` | Report v2 build, completion tier, HTML, persistence |

### 7.4 Evaluation Package

| Module | Responsibility |
|--------|----------------|
| `evaluation/rubric.py` | Weights, hire thresholds, noisy weights, profile aggregates |
| `evaluation/human_study_export.py` | CSV/JSON rows with empty `human_rating_*` columns |

---

## 8. End-to-End Interview Workflow

### 8.1 Candidate Voice Demo (Happy Path)

1. Start bot: `python backend/pipecat_integration/interview_bot.py`
2. Serve client: `python -m http.server 3000` from `manual_client/`
3. Browser opens UI; microphone permission granted; WebSocket connects to `ws://localhost:8765`
4. Client sends `start` (optional `resume_text`, `display_name`, `target_role`)
5. Adapter creates session; DialogueManager produces intro greeting; Cartesia speaks
6. Candidate answers; Deepgram streams transcripts; processor debounces and submits turns
7. Guards may redirect without scoring; otherwise evaluate → decide → next question TTS
8. Live UI receives `conversation_event` messages for chat bubbles and phase chips
9. Coverage engine advances through blueprint domains (probe once when weak)
10. On full coverage (or safety ceiling / explicit end), closing TTS plays
11. Report v2 saved under `reports/`; client auto-loads session-scoped report; HTTP `GET /latest-report` on `:8766` remains available

### 8.2 REST Text Path

1. `POST /start` → session + greeting
2. Repeated `POST /chat` with answers
3. `GET /report/{session_id}` or `GET /report/hr/{session_id}`
4. Optional `GET /export/human-study/{session_id}` for thesis validation data

### 8.3 Guard Outcomes (Non-Scored Turns)

Examples of behaviours that bypass the evaluator:

- Echo of the bot’s last question
- Meta: already answered / change topic / skip (with budget)
- IDK: rephrase → hint → skip domain
- Intent: repeat, clarification, audio issue
- Incomplete / tail fragment soft-continue
- Domain relevance redirect (semantic), capped to avoid loops

---

## 9. AI Pipeline

### 9.1 Speech-to-Text (Deepgram)

- Model default: `nova-2`
- Configurable endpointing, smart format, punctuation, technical keywords
- Interim and final frames merged with replace-when-extends logic (`merge_stt_hypothesis`)
- Cleanup: stutter prefixes, repeated n-grams (`transcript_utils`)

### 9.2 Voice Activity Detection and Interruption

- Silero VAD in the Pipecat pipeline
- **Barge-in:** server ignores VAD interrupts until bot has spoken for `BARGE_IN_MIN_BOT_SPEAK_SECONDS` (default 0.25s); client uses RMS thresholds
- Post-barge-in settle / echo cooldown / duplicate TTS suppress
- **Silence:** after bot stops speaking, nudge at ~8s and rephrase at ~15s if candidate remains silent (configurable; stage-locked)

### 9.3 Turn Finalisation and Tail Fragments

Live July 15–16 sessions showed early finalisation leaving short STT **tails** as separate turns (incomplete redirects, bad ADVANCE). Current mitigations:

- Resume window after substantial answers (`TURN_RESUME_WINDOW_SECONDS`, default 0.75s)
- Discard short tails after substantial submissions
- Incomplete/domain guards treat micro-fragments conservatively
- Decision engine scoring safety net for tail-like junk

Documented in `docs/VOICE_TAIL_FRAGMENT_FIX.md`.

### 9.4 Dialogue Management and LLM Orchestration

| Call site | Purpose |
|-----------|---------|
| `Evaluator.adaptive_evaluate` | Score answer + propose PROBE/ADVANCE and optional follow-up text |
| `EvaluationPipeline.rethink` | Second opinion on borderline scores |
| `LLMAdapter.generate` | Intro / new-domain / behavioural questions |
| Intent / Domain guards | Occasional classification / relevance LLM calls |
| `reporting.narrative` | Optional narrative summaries in Report v2 |

Adaptive path is primary; a legacy evaluate→decide→generate fallback remains if adaptive throws.

### 9.5 Evaluation Rubric

| Dimension | Weight | Profile |
|-----------|--------|---------|
| Structure | 0.25 | Communication |
| Result orientation | 0.20 | Technical |
| Ownership | 0.20 | Technical |
| Leadership | 0.15 | Technical |
| Clarity | 0.10 | Communication |
| Confidence | 0.10 | Communication |

**Per-answer hire signals:** Strong Hire ≥ 4.2, Hire ≥ 3.4, Borderline ≥ 2.5, else No Hire.

**Noisy STT weights** (when `is_noisy`): structure 0.12, result_orientation 0.24, ownership 0.24, leadership 0.16, clarity 0.04, confidence 0.10.

### 9.6 Reporting

`DialogueManager.get_final_report()` calls `reporting.generator.build_report_v2()`, which:

1. Uses legacy analytics as the evidence core
2. Classifies completion tier
3. Builds executive / domain / question-review sections
4. Optionally generates narrative text
5. Mirrors legacy keys for compatibility

Persistence writes JSON (+ HTML) via `reporting.persistence`; voice disconnect path uses the same module.

---

## 10. Backend Architecture and Service Interactions

```
manual_client
   │  WS audio + JSON control (start, interrupt)
   ▼
interview_bot  ── Deepgram / Cartesia services
   │
   ▼
InterviewProcessor ── VoiceTurnPolicy
   │                 ConversationEventPublisher
   ▼
InterviewDialogueAdapter
   ▼
SessionService ──► DialogueManager
                      │
                      ├─ GuardPipeline
                      ├─ Evaluator / EvaluationPipeline / rubric
                      ├─ DecisionEngine / CoverageEngine
                      ├─ LLMAdapter / prompts / question_dedup
                      ├─ analytics
                      └─ reporting.generator → persistence
                           │
                           └─ optional dialogue.database (Postgres)
```

**Async boundary:** Groq and dialogue adapter calls run in `asyncio.to_thread` from the Pipecat event loop so STT/TTS frames are not blocked (Phase 5).

**Deprecated path:** `InterviewFlowController` is not used on the Pipecat product path. Dev text WebSocket may still exist behind `ENABLE_DEV_TEXT_VOICE_WS` but is not the demo runtime.

---

## 11. Database and Storage

### 11.1 PostgreSQL (Optional)

Tables created on FastAPI startup when available:

| Table | Purpose |
|-------|---------|
| `sessions` | Session metadata, resume JSON, final score / hire signal |
| `responses` | Per-turn Q/A, scores, STAR breakdown, latency, decision type |

Functions: `create_tables`, `save_session`, `save_response`, `update_session_finals`, `get_latency_metrics`, `list_sessions`, …

If `DATABASE_URL` is unset or connection fails, the system continues with **in-memory sessions** and file-based reports. Missing `psycopg2` produces a warning and is non-blocking for local demos.

### 11.2 File Storage

| Path | Contents |
|------|----------|
| `reports/` | Completed / partial interview JSON (+ HTML) |
| `reports/aborted/` | Sessions with no evaluated turns |
| `logs/` | Application and optional live interview debug log |

### 11.3 What Is *Not* Stored as LLM Memory

Postgres and report files are **not** fed back into prompts. Continuity is selective fields on `InterviewContext` only.

---

## 12. APIs and Communication Flow

### 12.1 FastAPI REST (`main.py`, port 8000)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/start` | Create session + intro |
| POST | `/chat` | Process answer → next question + evaluation |
| GET | `/session/{session_id}` | Status + aggregates |
| GET | `/roles` | Available target roles |
| GET | `/health` | Health + active session count |
| GET | `/export/human-study/{session_id}` | κ-study export (`fmt=json\|csv`) |
| GET | `/report/{session_id}` | Full final report |
| GET | `/report/hr/{session_id}` | Recruiter report |
| GET | `/sessions` | List sessions |
| GET | `/sessions/rank` | Rank candidates |
| GET | `/sessions/{session_id}/summary` | Compact summary |

Optional when `ENABLE_DEV_TEXT_VOICE_WS=true`:

| Method | Path | Purpose |
|--------|------|---------|
| WS | `/ws/interview/{session_id}` | Dev text simulation |
| GET | `/voice/sessions` | List active dev voice sessions |

### 12.2 Pipecat Voice WebSocket (port 8765)

- Binary PCM audio up/down
- JSON control: `start`, `interrupt` (client `end` ignored so reconnect does not tear down STT/TTS)
- Server emits `conversation_event` payloads (`message`, `phase`, `session`) for the live UI

### 12.3 Report HTTP (port 8766)

- `GET /latest-report` — latest report artifact helper for demos
- Manual client prefers **session-scoped** report loading to avoid stale cross-session results

---

## 13. Configuration and Deployment

### 13.1 Environment Configuration

Copy `.env.example` → `.env`. Groups include:

- **Groq:** `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_EVALUATOR_MODEL`
- **Deepgram / Cartesia:** API keys, model, voice ID, STT tuning
- **Ports:** `PIPECAT_WS_HOST/PORT`, `REPORT_HTTP_PORT`
- **Voice timing:** debounce, grace, echo cooldowns, silence nudge/rephrase, barge-in grace, tail resume window / max words
- **Logging:** `LOG_LEVEL`, `PROCESSOR_LOG_FRAMES`, `DEBUG_LIVE_LOGGING`
- **Database:** `DATABASE_URL` (optional)
- **Flags:** `ENABLE_DEV_TEXT_VOICE_WS`

Canonical documentation: `docs/CONFIGURATION.md`.

### 13.2 Local Runbook

```powershell
cd AI-interviewer-fyp-v2
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt -r requirements-pipecat.txt
copy .env.example .env   # add keys

# Terminal 1 — voice bot
python backend\pipecat_integration\interview_bot.py

# Terminal 2 — browser client
cd backend\pipecat_integration\manual_client
python -m http.server 3000
# open http://localhost:3000

# Optional REST
uvicorn main:app --reload

# Regression
bash scripts/run_regression.sh
```

### 13.3 Deployment Reality

| Proposed / aspirational | Current |
|-------------------------|---------|
| Docker / AWS / GCP / Render | **Not implemented** |
| Multi-instance load balancing | **Not implemented** |
| Shared session store (Redis) | **Not implemented** — single-process memory |

Production demos today are **local machine** setups with cloud STT/TTS/LLM APIs.

---

## 14. Features Implemented Phase by Phase

Phased commits on `uthman` (see Appendix A). Summary of **what exists now**, mapped to phase intent:

### Phase 1 — Unified Core

- `SessionService` singleton for REST and voice
- Central config and interviewer policy extraction
- Removal of fragmented debug-session patterns

### Phase 2 — Dialogue Core / Guards

- Guard pipeline before scoring
- Transcript utilities, follow-up policy, output sanitizer
- Interviewer-mode persona (ask / redirect, do not coach)

### Phase 3 — Structured Flow & Optional Resume

- `role_registry`, `session_bootstrap`, `CoverageEngine`
- Resume-aware intro / project questions; default profile fallback
- Deprecation of `InterviewFlowController` on product path

### Phase 4 — Evaluation Engine

- Central `evaluation/rubric.py`
- Lite ensemble rethink on borderline answers
- Human-study export API
- Methodology metadata in reports

### Phase 5 — Production Hardening (Voice Operability)

- `VoiceTurnPolicy` + config-driven timing
- `asyncio.to_thread` for non-blocking Groq in Pipecat loop
- Structured logging; regression script; architecture docs
- Unified `_submit_turn` in `InterviewProcessor`

### Phase 6A — Interview Flow Quality

- Meta + IDK guards; question dedup; domain tracking fixes
- Skip-domain flows without scoring meta speech

### Phase 6B — Transcript Fairness

- Transcript quality assessment
- Noisy-STT reweighting of communication dimensions
- Deepgram tuning knobs

### Phase 6C — Reporting Clarity

- Communication vs technical score profiles
- `domain_assessment_map` with `not_assessed`
- Interview completion summary fields

### Phase 6 Voice Quality + Hotfixes

- Silence nudge/rephrase, STT merge quality, barge-in thresholds
- Natural opener rotation / softer redirects
- Reconnect without tearing down STT/TTS; interim silence fallback

### Post–Phase 6 Product Work (after report v1 snapshot `852bf7e`)

| Area | Implementation |
|------|----------------|
| Semantic domain relevance | LLM relevance checks; redirect caps |
| Modular manual client | `js/` + `styles/` architecture |
| **Report v2 package** | `backend/reporting/` + HTML + tiers |
| Live conversation wire | `conversation_event` end-to-end |
| Voice turn-taking QA | Premature interim gates, barge buffer, auto-load report |
| **Full blueprint coverage** | Turn ceiling 28; complete = 100% coverage; skip budget 2 |
| Repo cleanup | Removed unused root smoke scripts |
| **Tail fragment fix** | Processor resume window + guard/decision safety nets |
| **Recent Q&A memory** | Last 3 pairs in question prompts; sliding history |

---

## 15. Major Architectural Decisions

| Decision | Choice | Why (from code/docs/history) |
|----------|--------|------------------------------|
| Voice framework | Pipecat | Frame-based STT/TTS/VAD composition for live demos |
| LLM provider | Groq Llama 3.3 70B | Latency + JSON adherence for eval/questions |
| STT / TTS | Deepgram / Cartesia | Streaming quality vs Whisper-only / unspecified TTS |
| Frontend | Modular vanilla JS | Faster FYP delivery than React/Firebase rewrite |
| Adaptivity | Fixed blueprint + probes | Thesis-defensible without IRT item calibration data |
| Non-answer handling | Ordered guard pipeline | Live tests showed evaluator scoring echoes/meta/IDK |
| Sessions | In-process singleton | Sufficient for single-demo FYP; cross-process deferred |
| Reports | Dedicated `reporting/` v2 | Separates recruiter UX from analytics internals |
| Completion honesty | 100% coverage for `complete` | Mid-blueprint “complete” reports were misleading |
| Memory | Selective InterviewContext + recent Q&A | Avoid Memory Manager / RAG complexity for FYP |
| Emotion | Deferred | Scope, data, and integration cost vs voice robustness |

---

## 16. Improvements Since the Original Proposal

The original proposal envisioned multimodal emotion/facial analysis, a React/Firebase stack, and stronger psychometric adaptivity. The delivered system strengthened **voice dialogue robustness and evaluation methodology** instead.

| Aspect | Proposed (intent) | Implemented today |
|--------|-------------------|-------------------|
| Emotion / facial | SER + webcam CNN | Not implemented; text proxies via rubric |
| Adaptive testing | Dynamic / CAT-like | 10-domain Q-matrix + 1 probe/domain |
| Frontend | React.js | Modular HTML/JS manual client |
| Database | Firebase / MySQL | Optional PostgreSQL + JSON/HTML files |
| Deployment | Cloud containers | Local Python + `.env` (no Docker) |
| LLM | Unspecified / Gemini mentioned in some materials | **Groq** (not Gemini) |
| STT | Whisper-class | **Deepgram nova-2 streaming** |
| Interruption | Stress simulation | Functional barge-in + silence nudges |
| Evaluation | Multimodal fusion | Auditable 6-dim LLM rubric + rethink + fairness |

**Added beyond the proposal** because live testing demanded them: six-guard pipeline, Phase 6B transcript fairness, IDK policy, Report v2 tiers, live conversation UI events, full-coverage wrap policy, tail-fragment turn safety, recent Q&A prompt continuity.

---

## 17. Challenges Encountered and Resolutions

| Challenge | Evidence | Resolution |
|-----------|----------|------------|
| Non-answers scored as content | Phase 2 / 6A docs | Guard pipeline before evaluation |
| Domain / question loops | Phase 6A | `set_current_domain`, dedup, coverage fixes |
| Sync Groq blocking voice loop | Phase 5 | `asyncio.to_thread` in processor |
| Hardcoded voice timings | Phase 5 | `VoiceTurnPolicy` + `.env` |
| Unfair scores from noisy STT | Phase 6B | Quality assess + reweight |
| False barge-in / reconnect silence | Phase 6 hotfixes | Grace windows; no EndFrame teardown on soft disconnect |
| Interview ends mid-blueprint as “complete” | `FULL_COVERAGE_INTERVIEW.md` | Ceiling 28; complete needs 100% coverage |
| Soft “next question” skipped domains | Same | Stay-on-question vs hard skip budget |
| Early STT finalisation → orphan tails | `VOICE_TAIL_FRAGMENT_FIX.md` | Resume window + guard/decision nets |
| Stale `/latest-report` across sessions | Same | Session-scoped report client loading |
| Live transcript lost after hard reset | `WIRE_LIVE_CONVERSATION.md` | Re-wire `conversation_event` publisher ↔ UI |
| Weak follow-up continuity | `FYP_MEMORY_CONTINUITY.md` | Inject last 3 Q&A; sliding question window |

---

## 18. Current Implementation Status

### 18.1 Snapshot

| Item | Status |
|------|--------|
| Branch | `uthman` @ `64a7d784` (2026-07-16) |
| `main` branch | Frozen early (README era); **not** the product line |
| Phase 1–5 | Complete |
| Phase 6A–6C + voice quality | Complete |
| Report v2 + modular client | Complete |
| Full-coverage policy | Complete |
| Tail-fragment + recent Q&A memory | Complete |
| Official tests | `backend/tests/` (~21 modules) + regression script |
| Docker / multi-tenant / SER / facial / IRT | Not implemented |

### 18.2 Production Readiness Statement

Per Phase 6 completion notes and later QA docs: the system is **production-ready for dialogue/pipeline correctness** under automated regression, with **ongoing live-voice validation** recommended for silence/barge timing on each demo machine. README status lines that still say “Phase 5 complete” are **stale** relative to this report.

### 18.3 Known Soft Edges (Still True)

- Echo guard can occasionally misclassify real answers
- STT can still produce awkward chunks despite merge/cleanup
- Silence timing is wall-clock after bot-stop settle
- Barge-in is energy/VAD-based, not ASR-gated
- Cartesia chunk gaps not redesigned
- Human κ study export exists; human ratings not yet collected as an automated project deliverable

---

## 19. Remaining Work

Only items that are **genuinely unfinished** relative to proposal vision or documented follow-ups:

| Item | Priority | Notes |
|------|----------|-------|
| Human inter-rater (κ) validation study | High (thesis) | Export API ready |
| Docker / cloud deployment packaging | Medium–High | Not in repo |
| Speech emotion / facial analysis | Proposal-high, currently deferred | Explicit scope cut |
| Multi-role blueprints beyond Junior AI | Medium | Registry pattern ready |
| Multi-client / shared session store | Medium | Architecture limit today |
| React production frontend | Low–Medium | Manual client sufficient for FYP demo |
| Full IRT/CAT | Low (deferred) | Would need calibration data |
| ASR-gated barge-in; skip-after-double-silence | Low | Documented optional follow-ups |
| PDF export | Out of recent QA scope | HTML/JSON exist |
| Memory Manager / RAG / Redis | Explicitly rejected for FYP | See `FYP_MEMORY_CONTINUITY.md` |

---

## 20. Conclusion

This project delivers a working **real-time AI voice interviewer** with structured domain coverage, guarded dialogue, transparent LLM evaluation, and recruiter-oriented Report v2 output. Development followed a clear evolution: an initial monolithic prototype (June 2026), a five-phase modularisation (core → guards → coverage → evaluation → voice hardening), Phase 6 quality/fairness work, and a dense July stream of live-voice and reporting fixes culminating in full-blueprint coverage policy, tail-fragment safety, and recent Q&A continuity.

Where the original proposal emphasised multimodal emotion sensing and psychometric CAT, the team deliberately invested in **voice turn-taking reliability, non-answer handling, evaluation auditability, and honest completion reporting** — the failure modes that blocked a credible live demo. The result on branch `uthman` (commit `64a7d784`) is a coherent, testable system that someone can run locally, interview against a Junior AI Engineer blueprint, and obtain a versioned report with explicit limitations.

This **Version 2.0** report is the authoritative description of that system. Earlier narrative documents, including `FYP_FINAL_REPORT.md` (v1.0 / `852bf7e`), should be treated as historical.

---

## Appendix A — Git Evolution Timeline

Repository: `AI-interviewer-fyp-v2` · Remote: `origin` · Product branch: **`uthman`** · Tags: none · Linear history (24 commits at snapshot time).

| Date | Commit | Theme |
|------|--------|-------|
| 2026-06-24 | `de98129`, `0bf36d1` | Initial commit + README; **`main` stops** |
| 2026-06-29 | `65e6d91` … `6d1131f` | Refactors Phases 1–5 |
| 2026-07-03 | `017fd0d` | Disable Pipecat idle timeout |
| 2026-07-07 | `534b860`, `379744c`, `852bf7e` | Phase 6A–C + reconnect/speech capture + loop fixes *(v1 report snapshot)* |
| 2026-07-08 | `e832282` | Phase 6 voice quality completion |
| 2026-07-10 | `26f1195`, `64ac1a8`, `cb16cf6` | Semantic guards; modular client; **Report v2** |
| 2026-07-13–15 | `d253db4` … `4c5f1b4` | Dev log; turn-taking; live transcript wire; **full coverage**; cleanup |
| 2026-07-16 | `f69dd6c`, `0a3c7f9`, `64a7d784` | Tail-fragment fix + docs; **recent Q&A memory** |

Highest-churn modules historically: `dialogue_manager.py`, `interview_bot.py`, `interview_processor.py`.

---

## Appendix B — Documentation Index

| Document | Use |
|----------|-----|
| **This file (`FYP_FINAL_REPORT_V02.md`)** | Authoritative current FYP technical report |
| `dev_file.md` | Developer mental model through Report v2 era |
| `ARCHITECTURE.md` | Early runtime overview (pre–July additions) |
| `DIALOGUE_PIPELINE.md` | Guard/eval flow (guard list slightly pre–6A; code wins) |
| `INTERVIEW_FLOW.md` | Resume + coverage (Phase 3) |
| `CONFIGURATION.md` | Env vars including tail-fragment knobs |
| `PHASE_*_COMPLETE.md` | Phase deliverables 3–6 |
| `FULL_COVERAGE_INTERVIEW.md` | Coverage-first wrap-up policy |
| `VOICE_TURN_TAKING_FIXES.md` | July turn-taking QA |
| `VOICE_TAIL_FRAGMENT_FIX.md` | Tail fragment July 15/16 plan |
| `WIRE_LIVE_CONVERSATION.md` / `LIVE_CONVERSATION_TRANSCRIPT.md` | Live UI events |
| `FYP_MEMORY_CONTINUITY.md` / `memory.md` | Memory design + recent Q&A |
| `PROJECT_CLEANUP_REPORT.md` | Deleted vs retained artifacts |
| `FYP_FINAL_REPORT.md` | **Historical only** (v1.0 / `852bf7e`) |

---

*End of Report V2.0 — generated to match implementation on branch `uthman`, commit `64a7d784`.*
