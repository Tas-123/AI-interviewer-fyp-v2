# AI Interviewer FYP — Complete Developer Knowledge Document

This document is based on the current implementation in `AI-interviewer-fyp-v2` (branch `uthman`, through report v2). It is written so you can navigate, debug, extend, and explain the system without external help.

---

## Part 1 — Mental Model

Your project is a **real-time AI voice interviewer** with three faces and one brain:

| Face | Entry point | What it does |
|------|-------------|--------------|
| **Voice (primary)** | `backend/pipecat_integration/interview_bot.py` | WebSocket audio pipeline: mic → STT → dialogue → TTS |
| **REST API** | `main.py` (via `uvicorn`) | Text-based sessions for testing/integration |
| **Manual browser client** | `manual_client/index.html` | Demo UI that streams PCM audio to the voice server |

All three converge on:

```
SessionService → DialogueManager → (Guards → Evaluator → DecisionEngine → LLMAdapter)
```

The voice layer adds **timing policy** (debounce, barge-in, silence) in `InterviewProcessor`. The reporting layer wraps analytics into recruiter-facing **Report v2** in `backend/reporting/`.

---

## Part 2 — What Happens When the Application Starts

### Voice path (what you demo)

**Command:** `python backend/pipecat_integration/interview_bot.py`

**Execution order:**

1. **`interview_bot.py`** — `if __name__ == "__main__"` → `asyncio.run(run_bot())`
2. **`setup_logging()`** — configures log format/level from `core/logging_config.py`
3. **`core/config.py`** — `Settings` loads `.env`; creates `logs/`, `reports/`, `reports/aborted/`
4. **`start_report_http_server()`** — daemon thread on port **8766** serving `/latest-report`
5. **`InterviewDialogueAdapter()`** — gets singleton `SessionService`
6. **`JSONSerializer`** — parses client JSON control messages (`start`, `interrupt`; ignores `end`)
7. **`WebsocketServerTransport`** — binds **`ws://localhost:8765`**
8. **AI services initialized:**
   - `DeepgramSTTService` (STT)
   - `CartesiaTTSService` (TTS)
   - `InterviewProcessor` (your custom frame processor)
9. **`DiagnosticSileroVADAnalyzer`** + `VADProcessor` inserted before STT
10. **Pipeline assembled:**
    ```
    transport.input() → VADProcessor → DeepgramSTT → InterviewProcessor → CartesiaTTS → transport.output()
    ```
11. **`PipelineTask` + `PipelineRunner`** — event loop runs until killed

**Nothing happens in the dialogue engine until a client connects and sends `{"type":"start"}`**.

### REST path

**Command:** `uvicorn main:app --reload`

1. `main.py` loads `.env`, adds `backend/` to `sys.path`
2. `setup_logging()`, imports `SessionService`, `database`
3. FastAPI app created; optionally mounts `voice/websocket_router` if `ENABLE_DEV_TEXT_VOICE_WS=true`
4. `@app.on_event("startup")` → `db.create_tables()` (Postgres if available)
5. Waits for HTTP requests on port **8000**

### Configuration bootstrap

Everything reads from **`backend/core/config.py`** (`settings` singleton). Pipecat-specific re-exports live in **`backend/pipecat_integration/config.py`**. Browser client has its own **`manual_client/config.js`**.

---

## Part 3 — Complete Interview Lifecycle (24 Steps)

### Phase A — Connection & Session

#### 1. Candidate connects

- Browser opens WebSocket to `ws://localhost:8765`
- `on_client_connected` fires in `interview_bot.py`
- Client sends JSON: `{"type":"start", "target_role":"junior_ai_engineer", "display_name":"...", "resume_text":"..."}`

#### 2. Session is created

Chain:
```
JSONSerializer → ClientConnectedFrame
→ on_client_connected
→ adapter.start_interview(**start_payload)
→ SessionService.start_interview(session_start=...)
→ session_bootstrap.bootstrap_from_request()
→ DialogueManager(resume_data, session_id)
→ handle_turn("")   ← intro turn with empty transcript
```

**Files:** `integration/dialogue_adapter.py`, `core/session_service.py`, `dialogue/session_bootstrap.py`, `dialogue/dialogue_manager.py`

**Outputs:** `session_id`, intro greeting text, `InterviewContext` initialized with `CoverageEngine` and blueprint.

#### 3. Voice pipeline starts

- `interview_processor.session_id` set
- `reset_for_new_session()` clears buffers
- Greeting pushed as `TTSSpeakFrame(sanitize_tts_text(greeting))`
- Cartesia synthesizes audio → WebSocket → browser plays

---

### Phase B — Audio In → Transcript

#### 4. STT begins listening

- Browser sends **16 kHz mono PCM** binary frames
- `transport.input()` → `InputAudioRawFrame`
- **Silero VAD** (`VADProcessor`) detects speech start/stop
- **Deepgram** streams audio, emits:
  - `InterimTranscriptionFrame` (partial)
  - `TranscriptionFrame` (final, `finalized=True`)

**Config affecting STT:** `DEEPGRAM_MODEL`, `DEEPGRAM_ENDPOINTING_MS`, `DEEPGRAM_KEYWORDS`, etc.

#### 5. Audio is processed

Handled entirely in **`InterviewProcessor.process_frame()`**:

- VAD frames update speaking state
- STT frames update transcript buffer via `_merge_transcript_part()` → `merge_stt_hypothesis()` in `transcript_utils.py`
- Bot speaking frames update echo cooldown timers
- Client interrupt JSON → `request_client_interrupt()`

#### 6. Interim transcripts

While candidate speaks:
- Interim text merged into `_transcript_buffer`
- If bot is speaking → may trigger **barge-in** path (buffer, don't submit yet)
- `_note_candidate_activity()` cancels silence watch
- If VAD never fires stop, **`_schedule_interim_finalize()`** waits 1.4s silence then uses full **`transcript_debounce_seconds` (3.0s)**

#### 7. Final transcripts

On `TranscriptionFrame` with `finalized=True`:
- Merged into buffer
- **`_schedule_turn_debounce(final_transcript_debounce_seconds)`** — default **0.35s**
- After delay → `_prepare_transcript_for_turn()`

Also triggered by **`VADUserStoppedSpeakingFrame`** with same 0.35s debounce.

**Why two debounce values:** Final STT + VAD-stop should react fast; interim-only path waits longer for STT to stabilize.

---

### Phase C — Turn Gating & Submission

#### 8. Barge-in (interruption)

**Three layers:**

| Layer | Where | Trigger |
|-------|-------|---------|
| Client | `manual_client/js/audio/bargeInController.js` | RMS threshold while bot audio plays |
| Server control | `JSONSerializer` → `request_client_interrupt()` | Client sends `{"type":"interrupt"}` |
| Server STT/VAD | `InterviewProcessor._maybe_interrupt_bot()` | Speech during bot TTS after grace |

**Grace:** `BARGE_IN_MIN_BOT_SPEAK_SECONDS=0.25` — ignore first 250ms of bot speech unless STT has ≥3 words.

**Effect:** `broadcast_interruption()` stops TTS; transcript buffered for next turn submission.

#### 9. Silence detection

After bot stops and no buffered transcript:
- `_schedule_silence_watch()` → 0.85s settle
- At **8s** (`CANDIDATE_SILENCE_NUDGE_SECONDS`): nudge TTS
- At **15s** (`CANDIDATE_SILENCE_REPHRASE_SECONDS`): rephrase TTS

Cancelled by any candidate speech activity.

#### 10. Turn-taking management

**`VoiceTurnPolicy`** (`voice/voice_turn_policy.py`) centralizes thresholds from `settings`.

**`_prepare_transcript_for_turn()` gates:**

| Gate | Purpose |
|------|---------|
| Startup audio gate (4s) | Ignore mic during initial bot greeting |
| Bot echo cooldown (1.2s speaking / 0.8s after stop) | Prevent STT capturing bot TTS |
| Filler filter | Skip "ok", "um", etc. |
| Short answer grace (2.5s, ≤6 words) | Wait for continued speech |
| Duplicate skip | Same text as last processed turn |

Pass → **`_submit_turn()`** → `asyncio.to_thread(adapter.process_user_text, session_id, text)`

---

### Phase D — Dialogue Engine

#### 11. Dialogue Manager decides next action

**`DialogueManager.handle_turn(transcript)`** in `dialogue/dialogue_manager.py`:

```
prepare_transcript_for_evaluation()  ← transcript_utils + quality metadata
│
├─ INTRO + empty transcript → DecisionEngine.decide() → intro
├─ WRAPUP state → closing only
└─ Normal turn:
     GuardPipeline.run() ──triggered──→ _handle_guard_hit() [no scoring]
     │
     └── pass → Evaluator.adaptive_evaluate()
              → context.add_evaluation()
              → DecisionEngine.decide_from_adaptive()
              → choose next question (LLM or evaluator's next_question)
              → context.add_turn() + add_adaptive_trace()
              → DB persist
```

#### 12. Prompt construction

**`dialogue/prompts.py`** holds all system prompts:

| Prompt | Used for |
|--------|----------|
| `ADAPTIVE_EVALUATION_PROMPT` | Score + PROBE/ADVANCE decision (primary path) |
| `RETHINK_EVALUATION_PROMPT` | Borderline second pass |
| `INTRO_SYSTEM_PROMPT` | Greeting |
| `TECHNICAL_SYSTEM_PROMPT` | LLM-generated domain questions (fallback) |
| `FOLLOWUP_SYSTEM_PROMPT` | Weak-answer follow-ups |

Prompts enforce: one question, voice-friendly, no coaching, no markdown.

#### 13. LLM is called

**Groq** via:
- **`Evaluator._call_llm()`** — scoring/evaluation
- **`LLMAdapter._call_llm()`** — question generation

Both use `settings.groq_model` (default `llama-3.3-70b-versatile`).

Voice path runs dialogue in **`asyncio.to_thread()`** so Pipecat pipeline doesn't block.

#### 14. Question selection

**Primary questions** are mostly **deterministic** from blueprint:

1. `QuestionSelector` — resume-conditioned questions for `project_overview`, `behavioral_ownership`
2. Fixed question bank per domain — `_naturalize_static_question()` rotates openers
3. **LLM fallback** — when bank exhausted or domain needs dynamic wording

**`DecisionEngine._advance_to_next_domain()`** picks next uncovered blueprint domain.

#### 15. Follow-up questions

From **`Evaluator.adaptive_evaluate()`** decision:
- `PROBE` → evaluator's `next_question` (context-aware)
- `DecisionEngine` enforces `can_probe_domain()` (max 1 probe per domain)
- **Context follow-up** for strong answers (score ≥2.8, ≥18 words) in high-value domains

**`followup_policy.py`** classifies follow-up type (clarification, elaboration, etc.)

#### 16. Duplicate question prevention

**`question_dedup.py`:**
- `DOMAIN_PRIMARY_SIGNATURES` — phrase fingerprints per domain
- `is_semantic_duplicate()` — SequenceMatcher similarity
- `DialogueManager._ensure_unique_question()` — called before speaking a question

**Also:** `LLMAdapter._build_history_text()` feeds prior questions to LLM to avoid repeats.

#### 17. Conversation history

Stored in **`InterviewContext`**:
- `question_history[]` — every question asked
- `transcript_history[]` — every candidate answer
- `adaptive_trace[]` — full decision trace per turn (for reports)
- `evaluations[]` — scored turns only

**Not exported to report:** `non_evaluated_events` (internal guard audit).

#### 18. Interview state tracking

**Two parallel state concepts:**

| Concept | Type | Location |
|---------|------|----------|
| Interview phase | `InterviewState` enum | `context.state`: INTRO → TECHNICAL → WRAPUP |
| Blueprint progress | `CoverageEngine` | `domain_coverage`, `current_domain`, probe counts |
| Interview stage | EARLY/MID/LATE | `context.interview_stage` property (turn-based) |

**Guard state:** `guard_redirect_counts`, `domain_idk_counts`, `assessed_domains`, `skipped_domains`

#### 19. Coverage monitoring

**`CoverageEngine`** (`dialogue/coverage_engine.py`):

Blueprint order (from `core/interviewer_policy.py`):
```
project_overview → python → machine_learning → data_preprocessing →
model_evaluation → nlp_speech_ai → apis_backend → deployment →
debugging_problem_solving → behavioral_ownership
```

Limits:
- `MAX_TURNS_PER_DOMAIN = 1`
- `MAX_PROBES_PER_DOMAIN = 1`
- `MAX_TOTAL_INTERVIEW_TURNS = 12`
- `MAX_CONTEXT_FOLLOWUPS_TOTAL = 3`

When all domains covered or turn cap hit → `WRAPUP`.

---

### Phase E — Evaluation & Scoring

#### 20. Evaluation performed

**`EvaluationPipeline.evaluate_turn()`**:

1. Primary Groq call (`ADAPTIVE_EVALUATION_PROMPT`)
2. `apply_transcript_quality_adjustment()` if noisy STT
3. `compute_profile_scores()` — communication vs technical composites
4. Optional **rethink** if borderline (`should_trigger_rethink()`)
5. Return `{evaluation, decision, latency_ms, evaluation_method}`

**Guards skip evaluation entirely** — those turns appear in trace with `guard_passed: false`.

#### 21. Scores calculated

**`evaluation/rubric.py`** — single source of truth:

| Dimension | Weight |
|-----------|--------|
| structure | 0.25 |
| result_orientation | 0.20 |
| ownership | 0.20 |
| leadership | 0.15 |
| clarity | 0.10 |
| confidence | 0.10 |

`weighted_overall_score = Σ(dimension × weight)`

Per-answer hire signal: Strong Hire ≥4.2, Hire ≥3.4, Borderline ≥2.5, else No Hire.

Session-level signal (in analytics): slightly different thresholds (4.0/3.0/2.0).

---

### Phase F — Termination & Reporting

#### 22. Reports generated

On disconnect or explicit end:

```
adapter.end_interview(session_id)
→ SessionService.end_session()
→ DialogueManager.get_final_report()
   → generate_final_report(context)        [analytics.py — legacy aggregation]
   → sanitize_recruiter_summary...
   → build_report_v2(...)                  [reporting/generator.py]
→ save_interview_report()                  [JSON + HTML]
```

**Report v2 tiers** (`reporting/completion_policy.py`):

| Tier | Conditions |
|------|------------|
| **complete** | wrapup + ≥5 evaluated turns + ≥50% coverage |
| **partial** | ≥3 turns + ≥30% coverage |
| **incomplete** | below partial thresholds |
| **aborted** | 0 evaluated turns → saved to `reports/aborted/` |

Partial/incomplete → hire signal forced to **N/A**.

#### 23. Interview terminated

**Natural completion:**
- `DecisionEngine` returns closing action
- `InterviewProcessor` sees `is_complete=True`
- Speaks closing → waits `CLOSING_DELAY_SECONDS` → `EndTaskFrame`
- Client receives `{"type":"end"}` → disconnects

**Early disconnect:**
- Same report path runs; `termination_reason = user_disconnect`
- `interview_completion.completed = false` unless state was WRAPUP

#### 24. Cleanup

- `SessionService.end_session(remove=True)` drops session from memory
- WebSocket closes; Pipecat pipeline stays alive for next client
- Audio resources released on client side
- Report persisted to `reports/interview_report_{name}_{timestamp}_{id}.json` + `.html`
- Optional Postgres: `update_session_finals()`, `save_response()` per turn

---

## Part 4 — Subsystem Deep Dives

### 4.1 Voice Pipeline

**Why:** Bridges browser mic/speaker to dialogue engine without WebRTC complexity.

**Responsibility:** Binary PCM transport, frame routing, session lifecycle hooks.

**Key files:**
- `pipecat_integration/interview_bot.py` — assembly, WS lifecycle
- `pipecat_integration/interview_processor.py` — turn policy brain
- `voice/voice_turn_policy.py` — timing constants

**Communicates with:** Deepgram, Cartesia, `InterviewDialogueAdapter`

**Config:** All `TRANSCRIPT_*`, `BARGE_*`, `CANDIDATE_SILENCE_*`, VAD params (hardcoded in bot)

**If you change debounce down:** Faster responses but more partial STT submissions.  
**If you change debounce up:** Fewer false turns but sluggish feel.

---

### 4.2 STT Pipeline

**Why:** Convert speech to text for dialogue engine.

**Files:** Deepgram via Pipecat (`DeepgramSTTService`), merge logic in `transcript_utils.py`

**Post-processing:** `prepare_transcript_for_evaluation()`, `clean_live_transcript()`, `TranscriptQuality` scoring in `transcript_quality.py`

**Performance-sensitive:** Network latency to Deepgram; interim/final frame rate.

---

### 4.3 TTS Pipeline

**Why:** Speak interviewer questions naturally.

**Files:** Cartesia via Pipecat; `sanitize_tts_text()` strips coaching prefixes, handles LLM errors

**Performance-sensitive:** TTS queue depth; barge-in must interrupt Cartesia via `broadcast_interruption()`

---

### 4.4 Dialogue Manager

**Why:** Orchestrate one interview turn end-to-end.

**File:** `dialogue/dialogue_manager.py` — class `DialogueManager`

**Key methods:** `handle_turn()`, `_handle_guard_hit()`, `_ensure_unique_question()`, `get_final_report()`

**Tightly coupled to:** Guards, Evaluator, DecisionEngine, LLMAdapter, Context

---

### 4.5 Decision Engine

**Why:** Enforce interview *policy* on top of evaluator suggestions.

**File:** `dialogue/decision_engine.py`

**Key methods:** `decide_from_adaptive()`, `_advance_to_next_domain()`, probe limit logic

**Outputs:** Action dict: `{type: "ask"|"followup"|"closing", domain, topic, ...}`

---

### 4.6 Coverage Engine

**Why:** Ensure fair, complete blueprint coverage for Junior AI Engineer role.

**File:** `dialogue/coverage_engine.py`

**Isolated well** — pure domain progression logic; easy to extend for new roles via `role_registry.py`

---

### 4.7 Evaluation Engine

**Why:** Score answers consistently with rubric + optional ensemble rethink.

**Files:** `dialogue/evaluator.py`, `dialogue/evaluation_pipeline.py`, `evaluation/rubric.py`

**Isolated from voice** — could run in batch/offline.

---

### 4.8 Prompt System

**Why:** Centralize all LLM instructions; single place to tune interviewer behavior.

**File:** `dialogue/prompts.py`

**Also:** `core/interviewer_policy.py` — persona rules, coaching blocklist, closing copy

---

### 4.9 Memory / Context

**Why:** Single mutable session state bag.

**File:** `dialogue/context.py` — `InterviewContext`

**Persists in memory** for session lifetime; Postgres mirrors turns via `dialogue/database.py`

---

### 4.10 Guard Pipeline

**Why:** Filter bad STT, meta-talk, IDK, off-topic *before* expensive evaluation.

**File:** `dialogue/guards/pipeline.py`

**Order (first trigger wins):**
1. EchoGuard
2. MetaConversationGuard
3. IdkGuard
4. IntentGuard
5. IncompleteGuard
6. DomainGuard (LLM semantic relevance via `relevance.py`)

**Well isolated** — add new guard by implementing `Guard` protocol and registering in pipeline.

---

### 4.11 Logging

**Files:**
- `core/logging_config.py` — bootstrap
- `DEBUG_LIVE_LOGGING=true` → structured turn trace in `logs/live_interview_debug.log`

**Pipecat** has its own DEBUG frame logging (`PROCESSOR_LOG_FRAMES`).

---

### 4.12 Reporting

**Why:** Transform raw analytics into recruiter-facing artifact.

**Files:** `backend/reporting/*`, `dialogue/analytics.py`, `dialogue/recruiter_report.py`

**Report v2** separates recruiter summary from `detailed_analytics` (engineering audit).

---

### 4.13 Session Management

**File:** `core/session_service.py` — singleton `SessionService`

**In-memory dict** of active sessions; not shared across processes (Pipecat and uvicorn are separate processes unless you run combined).

---

### 4.14 Configuration Management

**File:** `core/config.py` — frozen `Settings` dataclass

**Loaded once at import.** Change `.env` → restart process.

---

### 4.15 API Layer

**File:** `main.py`

| Endpoint | Purpose |
|----------|---------|
| `POST /start` | Create session + intro |
| `POST /chat` | Text turn |
| `GET /report/{id}` | Full report |
| `GET /report/hr/{id}` | Recruiter subset |
| `GET /health` | Health check |
| `GET /roles` | Available target roles |

---

### 4.16 Background Workers

**No Celery/RQ.** Async concurrency via:
- Pipecat `PipelineRunner` event loop
- `asyncio.to_thread()` for Groq calls
- Report HTTP server — daemon `threading.Thread`

---

## Part 5 — Complete Data Flow Diagram

```
[CANDIDATE SPEAKS]
       │
       ▼
Browser mic → PCM 16kHz → WebSocket binary
       │
       ▼
VADProcessor (Silero) ──→ VADUserStarted/Stopped frames
       │
       ▼
DeepgramSTTService ──→ InterimTranscriptionFrame / TranscriptionFrame
       │
       ▼
InterviewProcessor
  ├─ merge_stt_hypothesis()
  ├─ debounce (0.35s final / 3.0s interim)
  ├─ echo/filler/short-answer gates
  ├─ barge-in coordination
  └─ _submit_turn() ──thread pool──▶
       │
       ▼
InterviewDialogueAdapter.process_user_text()
       │
       ▼
SessionService.process_turn()
       │
       ▼
DialogueManager.handle_turn()
  ├─ GuardPipeline ──(hit)──▶ redirect/skip (no eval)
  └─ (pass) ──▶ Evaluator.adaptive_evaluate()
                    │
                    ▼
              EvaluationPipeline → Groq (score + decision)
                    │
                    ▼
              DecisionEngine.decide_from_adaptive()
                    │
                    ▼
              LLMAdapter.generate() [if needed]
                    │
                    ▼
              Return {question, evaluation, decision_type}
       │
       ▼
InterviewProcessor → TTSSpeakFrame → CartesiaTTS → WebSocket audio
       │
       ▼
[CANDIDATE HEARS RESPONSE]

... repeat until WRAPUP ...

[DISCONNECT]
       │
       ▼
end_interview() → get_final_report()
  → analytics.generate_final_report()
  → reporting.build_report_v2()
  → save_interview_report() → reports/*.json + *.html
       │
       ▼
GET http://localhost:8766/latest-report
```

---

## Part 6 — Major File Reference

### Infrastructure / Core

| File | Role | Modify frequency |
|------|------|------------------|
| `core/config.py` | All env settings | **Often** (tuning) |
| `core/session_service.py` | Session CRUD | Rarely |
| `core/role_registry.py` | Role → blueprint mapping | When adding roles |
| `core/interviewer_policy.py` | Blueprint, limits, persona | When changing interview structure |
| `core/logging_config.py` | Log setup | Rarely |

### Voice

| File | Role | Modify frequency |
|------|------|------------------|
| `pipecat_integration/interview_bot.py` | Pipeline wiring | Rarely (infra) |
| `pipecat_integration/interview_processor.py` | Turn timing, barge-in, silence | **Often** (voice UX) |
| `voice/voice_turn_policy.py` | Policy dataclass | When adding timing params |
| `integration/dialogue_adapter.py` | Thin bridge | Rarely |

### Dialogue

| File | Role | Modify frequency |
|------|------|------------------|
| `dialogue/dialogue_manager.py` | Turn orchestration | **Often** (flow changes) |
| `dialogue/decision_engine.py` | Probe/advance policy | **Often** |
| `dialogue/coverage_engine.py` | Domain progression | When changing blueprint |
| `dialogue/context.py` | Session state | When adding state fields |
| `dialogue/llm_adapter.py` | Question generation | **Often** (question quality) |
| `dialogue/prompts.py` | All LLM prompts | **Often** |
| `dialogue/evaluator.py` | Scoring | When changing rubric behavior |
| `dialogue/guards/*.py` | Pre-eval filters | **Often** (false positive tuning) |
| `dialogue/question_dedup.py` | Duplicate prevention | When adding domains |
| `dialogue/transcript_utils.py` | STT merge/clean | **Often** (STT quality) |

### Evaluation & Reporting

| File | Role | Modify frequency |
|------|------|------------------|
| `evaluation/rubric.py` | Weights/thresholds | When changing scoring |
| `dialogue/analytics.py` | Legacy report aggregation | Moderate |
| `reporting/generator.py` | Report v2 assembly | Moderate |
| `reporting/completion_policy.py` | Completion tiers | Rarely |

### UI

| File | Role | Modify frequency |
|------|------|------------------|
| `manual_client/js/app.js` | Client entry | Moderate |
| `manual_client/js/network/voiceSession.js` | WS + audio | Moderate |
| `manual_client/js/ui/report/*` | Report display | When report schema changes |

### Deprecated (do not extend)

| File | Notes |
|------|-------|
| `dialogue/interview_flow_controller.py` | Superseded by CoverageEngine |
| `manual_client/client.js` | Deprecated shim |

---

## Part 7 — Dependency Map

```
                    ┌─────────────────┐
                    │  manual_client  │
                    └────────┬────────┘
                             │ WebSocket + HTTP
                             ▼
┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│   main.py    │───▶│ SessionService  │◀───│ interview_bot│
└──────────────┘    └────────┬────────┘    └──────┬───────┘
                             │                     │
                             ▼                     ▼
                    ┌─────────────────┐    ┌──────────────────┐
                    │ DialogueManager │◀───│ InterviewProcessor│
                    └────────┬────────┘    └──────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  GuardPipeline         Evaluator           DecisionEngine
        │                    │                    │
        ▼                    ▼                    ▼
  guards/*.py         EvaluationPipeline    CoverageEngine
                             │                    │
                             ▼                    ▼
                      evaluation/rubric    LLMAdapter
                             │                    │
                             └────────┬───────────┘
                                      ▼
                              InterviewContext
                                      │
                                      ▼
                           analytics.generate_final_report
                                      │
                                      ▼
                           reporting.build_report_v2
```

**Tight coupling hotspots:**
- `DialogueManager` ↔ guards/evaluator/decision/LLM (intentional orchestration)
- `InterviewProcessor` ↔ `VoiceTurnPolicy` ↔ `settings` (timing)
- `get_final_report()` ↔ analytics + reporting (recent addition)

**Well isolated:**
- `evaluation/rubric.py` (pure functions)
- `reporting/completion_policy.py`
- `question_dedup.py`
- `session_bootstrap.py`

---

## Part 8 — Operational Guide for You as Developer

### Files you'll modify most when adding features

| Goal | Start here |
|------|------------|
| New interview domain | `interviewer_policy.py` blueprint + `question_dedup.py` signatures + `LLMAdapter` bank |
| Better question wording | `prompts.py`, `llm_adapter.py` |
| Fix false redirects | `guards/domain_guard.py`, `guards/relevance.py` |
| Fix STT merge issues | `transcript_utils.py`, `interview_processor.py` |
| Tune voice responsiveness | `.env` debounce/barge-in vars, `voice_turn_policy.py` |
| Change scoring | `evaluation/rubric.py`, `prompts.py` (ADAPTIVE_EVALUATION) |
| Report content/layout | `reporting/builders.py`, `renderers/html_renderer.py` |
| New REST endpoint | `main.py` |

### Files to treat as core infrastructure (change carefully)

- `core/session_service.py`
- `integration/dialogue_adapter.py`
- `pipecat_integration/interview_bot.py` (pipeline order)
- `evaluation/rubric.py` (breaks report comparability)
- `dialogue/context.py` (many dependents)

### Safe to tune via `.env`

| Variable | Effect |
|----------|--------|
| `FINAL_TRANSCRIPT_DEBOUNCE_SECONDS` | Response speed vs STT completeness |
| `TRANSCRIPT_DEBOUNCE_SECONDS` | Interim-only path delay |
| `BARGE_IN_MIN_BOT_SPEAK_SECONDS` | Interruption sensitivity |
| `CANDIDATE_SILENCE_NUDGE/REPHRASE_SECONDS` | Silence prompts |
| `BOT_ECHO_COOLDOWN_*` | Echo false triggers |
| `GROQ_MODEL` | Question/eval quality vs speed |

### Performance-sensitive areas

1. **Groq LLM calls** — 1–2 per turn (eval + optional rethink + maybe question gen)
2. **Deepgram streaming** — network bound
3. **Cartesia TTS** — latency affects perceived responsiveness
4. **`asyncio.to_thread`** — thread pool size under concurrent load
5. **Guard LLM calls** — DomainGuard/relevance adds latency on edge cases

### Technical debt & risks

| Risk | Detail |
|------|--------|
| **Single-session Pipecat runner** | One active WS client; not multi-tenant |
| **In-memory sessions** | Pipecat and FastAPI are separate processes — sessions don't cross |
| **`/latest-report` by mtime** | Not session-scoped; can show wrong report if multiple runs |
| **Guard LLM dependency** | Domain relevance fails open on LLM error (defaults to relevant) |
| **Hardcoded VAD params** | Not in `Settings`; requires code change to tune |
| **Pipecat deprecation warnings** | `WebsocketServerTransport`, `PipelineTask` deprecated in Pipecat 1.4+ |
| **Dual report shapes** | v2 + legacy keys mirrored at root — transitional complexity |
| **PostgreSQL optional** | DB failures silently fall back; reports still file-based |

### Suggested future improvements (no implementation)

1. Session-scoped report endpoint (`/reports/{session_id}`)
2. Move VAD params into `Settings`
3. Structured `termination_reason` passed explicitly from disconnect handler
4. PDF export via HTML renderer (WeasyPrint/Playwright)
5. Multi-role blueprint registry with UI role picker
6. Integration tests with recorded STT fixtures (deterministic voice testing)
7. Separate processes: shared session store (Redis) if scaling beyond demo
8. Consolidate HR report (`recruiter_report.py`) into Report v2 single schema

---

## Part 9 — How to Debug Common Issues

| Symptom | Trace path |
|---------|------------|
| Bot doesn't respond after speech | `InterviewProcessor` logs → debounce → `_prepare_transcript_for_turn` gates |
| Infinite redirects | `adaptive_trace` → `DOMAIN_RELEVANCE_REDIRECT` → `guard_redirect_counts` |
| Same question repeated | `question_dedup.py` → `_ensure_unique_question` → `question_history` |
| Can't interrupt bot | Client barge-in config + `BARGE_IN_MIN_BOT_SPEAK_SECONDS` + server logs for `broadcast_interruption` |
| Wrong report shown | Check `reports/` filename vs session; `/latest-report` picks newest file |
| Empty evaluation | Guard triggered — check `guard_passed: false` in trace |
| Slow turns | Groq latency in return `latency_ms`; check rethink triggered |

**Best debug tool:** `DEBUG_LIVE_LOGGING=true` → `logs/live_interview_debug.log`

**Regression:** `bash scripts/run_regression.sh`

---

## Part 10 — Documentation Map (What's Already Written)

| Doc | Use when |
|-----|----------|
| `docs/ARCHITECTURE.md` | Quick runtime overview |
| `docs/DIALOGUE_PIPELINE.md` | Guard + turn flow |
| `docs/INTERVIEW_FLOW.md` | Session bootstrap + coverage |
| `docs/CONFIGURATION.md` | Every env var |
| `docs/PHASE_*_COMPLETE.md` | Historical phase deliverables |
| `docs/FYP_FINAL_REPORT.md` | Academic write-up |
| `manual_client/README.md` | Browser client architecture |

---

This document reflects the codebase as implemented today. After reading it, you should be able to: trace any utterance from mic PCM to report JSON, explain why each subsystem exists, know which files to open for any bug class, and extend the system (new domains, guards, report sections, or voice tuning) without guessing where logic lives.
