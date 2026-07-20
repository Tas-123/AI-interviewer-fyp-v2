# Phase 1 Prep — Architecture & Mental Model

**Goal after this doc:** You can draw the system on a whiteboard, name every major box, explain how the pieces talk to each other, and answer “where does the AI logic live?” without hesitation.

**Tracker:** [`FYP_LEARNING_PHASES.md`](FYP_LEARNING_PHASES.md)  
**Code authority:** branch `uthman`  
**Companion short diagram:** [`ARCHITECTURE.md`](ARCHITECTURE.md)

Mark Phase 1 as `reading` in the tracker while you study this.

---

## 1. What this project is (one clear sentence)

This FYP is a **real-time AI voice interviewer** for Junior AI Engineer candidates: the candidate speaks in a browser, the system transcribes speech, runs a structured multi-domain interview, evaluates answers with an LLM rubric, asks adaptive follow-ups, and writes a recruiter-facing report (JSON + HTML).

It is **not** primarily a frontend showcase. The value is in:

- streaming voice turn-taking (STT / VAD / TTS / barge-in)
- a guarded dialogue engine that does not score garbage as answers
- coverage-first interview structure
- transparent evaluation + honest reporting

Emotion recognition (SER / facial), IRT/CAT psychometrics, React/Firebase, Docker/cloud multi-tenant, and RAG memory are **not** in the delivered system. Know that for defense — Phase 9 covers *why*.

---

## 2. The one idea you must own: “Three faces, one brain”

```
┌────────────────────────────┐     ┌─────────────────────────┐
│  Face A — Voice product    │     │  Face B — REST testing  │
│  interview_bot.py          │     │  main.py (FastAPI)      │
│  WS :8765 + report :8766   │     │  REST :8000             │
└─────────────┬──────────────┘     └────────────┬────────────┘
              │                                 │
              └──────────────┬──────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │   SessionService     │  ← session store (in-process)
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │  DialogueManager     │  ← the interview “brain”
                  │  guards → eval →     │
                  │  decide → generate   │
                  └──────────────────────┘

Face C — Browser UI (manual_client on :3000)
  talks to Face A over WebSocket audio + JSON control messages
  loads reports from Face A’s report HTTP (:8766)
```

### What this means in plain language

| Piece | Role |
|-------|------|
| **Faces** | Different ways to *enter* the system (mic voice, REST text, browser UI) |
| **SessionService** | One place that creates/finds sessions and routes turns |
| **DialogueManager** | One place that decides what happens next in the interview |

**Board-ready line:**  
“We separated *transport* from *interview logic*. Voice and REST are transports. All interview intelligence lives in DialogueManager behind SessionService, so scoring and questioning stay consistent whether you type or speak.”

---

## 3. The three runtimes (ports and commands)

| Runtime | Command | Ports | Is it the product? |
|---------|---------|-------|--------------------|
| **Pipecat voice bot** | `python backend/pipecat_integration/interview_bot.py` | WS **8765**, report HTTP **8766** | **Yes — primary demo** |
| **FastAPI REST** | `uvicorn main:app --reload` | **8000** | Testing / text turns / reports API |
| **Manual client** | `python -m http.server 3000` inside `manual_client/` | **3000** | Demo UI (not React) |

Optional fourth path (dev only): text WebSocket on FastAPI when `ENABLE_DEV_TEXT_VOICE_WS=true`. That is **not** the live voice product; it simulates turns with text.

### Critical process fact

`SessionService` is an **in-process singleton**.

- Same Python process → shared sessions  
- Voice bot process and FastAPI process started separately → **two different stores**

For demos, the voice bot alone is enough. Do not claim “REST and voice share sessions across processes” unless both run in one process (they usually don’t).

---

## 4. Folder map (what lives where)

```text
AI-interviewer-fyp-v2/
├── main.py                          # Face B — FastAPI
├── requirements.txt                 # FastAPI, Groq, Postgres driver, …
├── requirements-pipecat.txt         # Pipecat + Deepgram + Cartesia + Silero
├── .env / .env.example              # API keys + voice timing
├── docs/                            # Architecture, phase reports, FYP reports
├── reports/                         # Generated interview JSON + HTML
├── logs/                            # Optional live debug logs
├── scripts/run_regression.sh        # Official test harness
└── backend/
    ├── core/                        # Config, SessionService, policy, roles
    ├── dialogue/                    # Brain: managers, guards, eval, LLM
    ├── evaluation/                  # Rubric weights + human-study export
    ├── integration/                 # Thin adapter: Pipecat ↔ SessionService
    ├── pipecat_integration/         # Voice bot + InterviewProcessor + UI
    ├── reporting/                   # Report v2 builders + HTML
    ├── voice/                       # VoiceTurnPolicy (+ legacy/dev simulators)
    └── tests/                       # Regression / phase tests
```

### Package cheat-sheet

| Package | Owns |
|---------|------|
| `backend/core/` | Settings, session singleton, role registry, interviewer policy constants |
| `backend/dialogue/` | Turn orchestration, guards, evaluator calls, decisions, prompts, coverage |
| `backend/evaluation/` | Rubric definitions (weights, hire thresholds, noisy weights) |
| `backend/integration/` | `InterviewDialogueAdapter` — plain-text bridge for the voice path |
| `backend/pipecat_integration/` | Pipeline assembly, frame processor, browser client |
| `backend/reporting/` | Report v2 JSON/HTML persistence |
| `backend/voice/` | Timing policy used by the processor; **dev** text-voice helpers |

---

## 5. Key files for Phase 1 (read names → know jobs)

You do **not** need line-by-line mastery yet. You need “what is this file for?”

| File | Job |
|------|-----|
| `backend/pipecat_integration/interview_bot.py` | Assembles STT → processor → TTS; opens WS :8765; starts report HTTP :8766 |
| `backend/pipecat_integration/interview_processor.py` | Voice turn logic: debounce, barge-in, silence, submit transcript to brain |
| `backend/integration/dialogue_adapter.py` | `start_interview` / `process_user_text` / `end_interview` → SessionService |
| `backend/core/session_service.py` | Create/get/process/end sessions; holds `DialogueManager` per session |
| `backend/dialogue/dialogue_manager.py` | `handle_turn` — the central interview algorithm |
| `main.py` | REST routes (`/start`, `/chat`, `/report/...`) for text testing |
| `backend/core/config.py` | Loads `.env` into settings |
| `backend/core/interviewer_policy.py` | Blueprint domains, turn limits, persona / spoken copy |
| `backend/pipecat_integration/manual_client/` | Browser mic UI |

**Deprecated / not product path (do not defend as current):**

- `backend/dialogue/interview_flow_controller.py` — superseded by `CoverageEngine` + `DialogueManager`
- Most of `backend/voice/*` except `voice_turn_policy.py` — older text-simulation stack; live voice uses Pipecat

---

## 6. How modules communicate (the call chain)

### Product path (what you demo)

```text
Browser mic (PCM over WebSocket)
    → interview_bot (Pipecat pipeline)
        → Silero VAD (speech boundaries)
        → Deepgram STT (text hypotheses)
        → InterviewProcessor
              • merge / debounce / echo / barge-in / silence / tail handling
              • publish conversation_event for UI bubbles
              • asyncio.to_thread(… process_user_text …)
                    → InterviewDialogueAdapter
                          → SessionService.process_turn / start_interview
                                → DialogueManager.handle_turn
                                      → guards → evaluate → decide → LLM generate
        → Cartesia TTS (spoken reply)
    → WebSocket audio + JSON events back to browser
    → on end: reporting writes reports/*.json + *.html
    → client may fetch report via :8766
```

### Testing path (no mic)

```text
POST /start  → SessionService.start_interview → intro question
POST /chat   → SessionService.process_turn → next question + evaluation fields
GET  /report/{id} → report payload for that session
```

### Adapter role (important)

`InterviewDialogueAdapter` does **not** contain interview intelligence. It only:

1. starts a session
2. passes user text in
3. returns a dict with `ai_response_text`, state, completion flags, etc.

That keeps Pipecat free of dialogue rules and keeps dialogue free of audio frames.

---

## 7. What’s inside the “brain” (preview only — Phase 4 goes deep)

Every scored turn roughly does:

```text
clean transcript
  → GuardPipeline (first match wins): Echo → Meta → IDK → Intent → Incomplete → Domain
  → Evaluator (Groq rubric + optional rethink + STT fairness)
  → DecisionEngine (PROBE / ADVANCE / wrap rules via CoverageEngine)
  → LLMAdapter (new question when needed)
  → sanitize + store canonical question + update InterviewContext
```

**Why architecture matters here:** the voice layer must deliver *good text turns* into this pipeline. The pipeline must refuse to score echoes, “repeat that?”, IDK, and off-topic speech as if they were technical answers.

---

## 8. Tech stack (what to say confidently)

| Layer | Choice | One-line why |
|-------|--------|--------------|
| Voice framework | **Pipecat** | Frame-based composition of STT/TTS/VAD for live demos |
| STT | **Deepgram nova-2** | Streaming transcription quality |
| VAD | **Silero** (via Pipecat) | Detect when the user starts/stops speaking |
| TTS | **Cartesia** | Low-latency spoken interviewer voice |
| LLM | **Groq** `llama-3.3-70b-versatile` | Latency + JSON-ish structure for eval/questions |
| REST | **FastAPI** | Text testing and report APIs |
| Frontend | **Vanilla HTML/JS** (modular) | Faster FYP delivery than a React rewrite |
| Storage | In-memory sessions + file reports; **optional Postgres** | Demo-first; DB is nice-to-have persistence |

Cloud APIs (Deepgram / Cartesia / Groq) do the heavy ML. Your contribution is the **orchestration, dialogue policy, evaluation methodology, and voice turn-taking design**.

---

## 9. Dual dependency files

- `requirements.txt` — FastAPI path + Groq + Postgres driver, etc.
- `requirements-pipecat.txt` — Pipecat extras (`deepgram`, `cartesia`, `websocket`, `silero`)

Voice demos need **both**. REST-only testing can run with the first alone (still needs Groq key for LLM turns).

---

## 10. Data that exists vs data that does not

### Exists

| Store | What |
|-------|------|
| In-process `SessionService` dict | Live `InterviewSession` + `DialogueManager` / `InterviewContext` |
| `reports/` | Report v2 JSON + HTML |
| `logs/` | Optional debug (e.g. `DEBUG_LIVE_LOGGING`) |
| Optional Postgres | Sessions/responses if `DATABASE_URL` works |

### Does **not** exist (common misconception)

| Myth | Reality |
|------|---------|
| Full chat `messages[]` history sent to Groq every turn | **No** — selective context (recent Q&A, sliding question window, resume fields) |
| Redis / shared session store across machines | **No** — single-process memory |
| RAG / vector memory | **No** — intentionally deferred |
| Separate microservice per STT/TTS/dialogue | **No** — one Pipecat process + libraries/APIs |

Memory design is Phase 3/4/9 territory; for Phase 1 just remember: **InterviewContext is the live state, not a chat log replay.**

---

## 11. How architecture evolved (enough for Phase 1)

| Era | What landed |
|-----|-------------|
| Phase 1 | Unified `SessionService` + config so REST and voice share one brain *in-process* |
| Phase 2 | Guard pipeline + interviewer persona |
| Phase 3 | CoverageEngine + optional resume bootstrap |
| Phase 4 | Rubric + rethink ensemble + human-study export |
| Phase 5 | VoiceTurnPolicy, async Groq (`asyncio.to_thread`), logging, regression |
| Phase 6+ | Flow quality, STT fairness, Report v2, barge-in/silence/tail fixes, live UI events, coverage-first wrap, canonical questions, lobby |

**Architectural constant across all of that:** SessionService → DialogueManager stayed the center. Most “hard” bugs were at the **voice edges** (turn-taking, STT noise, TTS stacking) or **policy honesty** (when is an interview “complete”?), not “we rewrote the brain every week.”

---

## 12. Design decisions you should already be able to defend (Phase 1 level)

| Decision | Choice | Short why |
|----------|--------|-----------|
| Framework | Pipecat | Real-time frame pipeline for STT/TTS/VAD |
| LLM | Groq | Speed for live interview loops |
| Frontend | Modular vanilla JS | Scope control for FYP |
| Sessions | In-process singleton | Enough for single-demo; Redis deferred |
| Separation | Adapter + SessionService | Keep audio code out of dialogue rules |
| Emotion / CAT / RAG | Deferred | Live voice reliability + evaluation honesty mattered more |

Deeper trade-offs = Phase 9. Here you only need the architecture-level story.

---

## 13. Common mistakes and misconceptions

1. **“The chatbot is Cartesia / Deepgram.”**  
   Those are speech I/O. Interview logic is DialogueManager.

2. **“FastAPI is the main app.”**  
   FastAPI is the testing face. The demo product is `interview_bot.py`.

3. **“manual_client is a React app.”**  
   It is modular vanilla HTML/CSS/JS under `pipecat_integration/manual_client/`.

4. **“Starting REST and voice shares one session store.”**  
   Only if same process. Separate terminals = separate stores.

5. **“InterviewFlowController still drives interviews.”**  
   Deprecated. CoverageEngine + DialogueManager own the product path.

6. **“README status lines are always current.”**  
   Prefer `FYP_FINAL_REPORT_V03.md` + live `uthman` code. README can lag (e.g. still saying “Phase 5 complete”).

7. **“We implemented emotion analysis because it’s in the title.”**  
   Proposal title mentions emotion; delivery uses text rubric proxies. Be honest — board respects scoped honesty.

8. **“Everything in `backend/voice/` is production voice.”**  
   Production timing policy yes (`voice_turn_policy.py`). Orchestrator/simulator files are mostly legacy/dev.

---

## 14. Board-style questions (Phase 1) + how to answer

### Q1. Explain your system architecture.

**Answer frame:**  
“We have three faces and one brain. The primary face is a Pipecat WebSocket voice server on 8765 with Deepgram STT, Silero VAD, and Cartesia TTS. A FastAPI REST API on 8000 supports text testing. The browser client streams audio to the voice bot. Both voice and REST go through SessionService into DialogueManager, which runs guards, evaluation, decision, and question generation. Reports are written as Report v2 JSON/HTML.”

### Q2. Where is the AI logic?

**Answer frame:**  
“Groq is the LLM provider. The *application* AI logic — when to probe, skip, wrap, refuse non-answers, and how to score — is in DialogueManager and its modules under `backend/dialogue/` and `backend/evaluation/`. Pipecat handles streaming I/O.”

### Q3. Why not put all logic inside the Pipecat processor?

**Answer frame:**  
“So REST and voice share identical interview behavior, and so we can unit-test dialogue without a microphone. The processor handles turn-taking; the adapter passes clean text into SessionService.”

### Q4. What happens if FastAPI and the voice bot both run?

**Answer frame:**  
“They are separate processes with separate SessionService singletons unless we deliberately run them together. Live demos use the voice bot; REST is for text regression and API access.”

### Q5. What is your contribution vs third-party APIs?

**Answer frame:**  
“Deepgram/Cartesia/Groq/Pipecat provide building blocks. Our contribution is the end-to-end interview system: guarded dialogue, coverage policy, adaptive probing, rubric evaluation with fairness, interruption handling, and recruiter reporting.”

### Q6. Is this a frontend project?

**Answer frame:**  
“No. The UI is a thin demo client. The research and engineering depth are in voice turn-taking and the dialogue/evaluation pipeline.”

### Q7. Draw the voice data path.

**Answer frame (say while drawing):**  
Mic → WS → VAD → STT → InterviewProcessor → (thread) Adapter → SessionService → DialogueManager → TTS → WS → speaker; plus conversation events and final report files.

---

## 15. Self-check (close the doc, answer aloud)

If you can answer all of these cleanly, mark Phase 1 `self-checked` / `done` in the tracker.

1. What does “three faces, one brain” mean?
2. Name the three ports used in a typical demo (WS, report HTTP, client).
3. Which file is the primary product entry point?
4. What does SessionService store, and what is its process limitation?
5. What does InterviewDialogueAdapter do *and not* do?
6. Name the four high-level stages inside DialogueManager’s turn handling.
7. Which packages own: rubric, report HTML, voice pipeline, REST API?
8. Name two deprecated/non-product paths people confuse with the live system.
9. What cloud services do STT, TTS, and LLM?
10. Why is emotion analysis not a delivered module despite the proposal title?

---

## 16. Suggested file skim order (30–40 minutes)

After reading this doc once:

1. `docs/ARCHITECTURE.md` (confirm diagram)
2. `backend/core/session_service.py` (class docstring + `create` / process methods)
3. `backend/integration/dialogue_adapter.py` (three public methods)
4. `main.py` (route list at a glance)
5. Top of `backend/pipecat_integration/interview_bot.py` (pipeline comment + report server)
6. Folder list under `backend/dialogue/` and `backend/pipecat_integration/manual_client/`

Do **not** deep-dive `interview_processor.py` or `dialogue_manager.py` yet — those are Phases 4–5.

---

## 17. One-paragraph “elevator” for presentations

> Our system is an AI voice interviewer with a clear separation of concerns: a Pipecat streaming voice face for live interviews, a FastAPI face for testing, and a browser client for demos. All of them share one interview brain — SessionService and DialogueManager — so transcription, evaluation, adaptive questioning, and reporting stay consistent. Third-party STT, TTS, and LLM services handle speech and language primitives; our engineering contribution is the real-time orchestration, dialogue policy, evaluation methodology, and recruiter report pipeline.

---

## Next

When Phase 1 self-check feels solid, say **“Phase 2”** and we will create `FYP_PREP_PHASE_2_…` (end-to-end interview lifecycle) and update the tracker.

*If anything in this prep doc conflicts with live code on `uthman`, trust the code and update this doc.*
