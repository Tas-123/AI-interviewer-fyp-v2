# Main Code Components — Group Share Doc

**Project:** AI Powered Interview Simulation and Feedback Platform  
**Audience:** Team members (presentation + viva defense)  
**Purpose:** Know what each major module does, where it lives, and one line you can say confidently.

---

## 1. Big picture (say this in 20 seconds)

> The system has three surfaces: a **recruiter dashboard**, a **candidate lobby/voice UI**, and a **Pipecat voice bot**. The interview “brain” is **DialogueManager**. Around it sit **SessionService** (session registry), **GuardPipeline** (conversational control), **Evaluator** (scoring), **DecisionEngine** + **CoverageEngine** (policy), **LLMAdapter** (spoken questions), and **Report V2** (final feedback).

```
Recruiter (:8001)  →  Invite token
Candidate (:3000)  →  Lobby → WebSocket voice (:8765)
                         │
   Silero VAD → Deepgram STT → InterviewProcessor
                         │
              SessionService → DialogueManager
                         │
     Guards → Evaluator → DecisionEngine/Coverage → LLMAdapter
                         │
              Cartesia TTS → Candidate hears next question
                         │
              Report V2 → saved → recruiter views (:8766 / dashboard)
```

| Port | What runs | Role |
|------|-----------|------|
| **8001** | Recruiter FastAPI | Login, create invites, browse reports |
| **3000** | Candidate UI | Lobby + live interview screen |
| **8765** | Pipecat voice bot | Real-time audio interview |
| **8766** | Report HTTP helper | Latest report JSON/HTML |
| **8000** | Optional FastAPI | Text/API testing only (not main product path) |

---

## 2. Component cheat sheet

### SessionService
**File:** `backend/core/session_service.py`

**What it is:** The session registry for the whole process. Creates and looks up each interview’s `DialogueManager`.

**Why it matters:** Voice bot and optional REST API both go through one place, so session lifecycle is consistent (`create` → `start_interview` → `process_turn` → `end_session`).

**Say in viva:**  
“SessionService is our single session store so every turn for a candidate hits the same DialogueManager.”

---

### InterviewContext
**File:** `backend/dialogue/context.py`

**What it is:** The mutable “blackboard” for one interview: state, question history, evaluations, adaptive traces, coverage helpers.

**Why it matters:** Guards, DecisionEngine, Evaluator, and Report V2 all read/write this object. Without it, the system would forget what already happened.

**Say in viva:**  
“InterviewContext holds everything about the ongoing interview—domains covered, scores, and history.”

---

### DialogueManager
**File:** `backend/dialogue/dialogue_manager.py`

**What it is:** The **main interview brain**. One method drives most of the logic: `handle_turn(transcript)`.

**What one turn does (order):**
1. Clean / prepare transcript  
2. Run **GuardPipeline** (may stop early)  
3. If OK → **Evaluator** scores + suggests PROBE/ADVANCE  
4. **DecisionEngine** applies hard policy (with **CoverageEngine**)  
5. **LLMAdapter** generates spoken wording when needed  
6. Update context; return next question (+ evaluation metadata)

**Say in viva:**  
“DialogueManager orchestrates each turn: guards first, then score and decide, then generate the next question under coverage policy.”

---

### GuardPipeline (conversational control)
**Folder:** `backend/dialogue/guards/`  
**Pipeline:** `pipeline.py`

**What it is:** Checks that run **before** scoring. If a guard triggers, we respond / redirect and usually **do not** treat the turn as a full scored answer.

**Order (fixed):**

| # | Guard | Catches |
|---|--------|---------|
| 1 | **EchoGuard** | Bot hears its own question (STT echo) |
| 2 | **MetaConversationGuard** | “Skip”, “already answered”, soft topic control |
| 3 | **IdkGuard** | “I don’t know” / hint requests |
| 4 | **IntentGuard** | Repeat, clarify, off-topic, audio issues |
| 5 | **IncompleteGuard** | Tiny / broken STT fragments |
| 6 | **DomainGuard** | Answer not relevant to current question |

**Say in viva:**  
“Guards are conversational control before scoring—we don’t grade echoes, IDKs, or incomplete STT as real answers.”

---

### Evaluator (+ EvaluationPipeline)
**Files:** `backend/dialogue/evaluator.py`, `evaluation_pipeline.py`  
**Rubric:** `backend/evaluation/rubric.py`

**What it is:** LLM-based scoring of candidate answers on six dimensions, and a suggested next move (`PROBE` / `ADVANCE`).

**Dimensions (weights sum to 1):** structure, result orientation, ownership, leadership, clarity, confidence.

**Hire bands (overall):**  
≥ **4.0** Strong Hire · ≥ **3.0** Hire · ≥ **2.5** Borderline · else No Hire

**Say in viva:**  
“Evaluator grades the answer on a fixed rubric and suggests probe or advance; DecisionEngine can still override for policy.”

---

### DecisionEngine
**File:** `backend/dialogue/decision_engine.py`

**What it is:** Hard **policy layer** on top of the LLM suggestion.

**Main decisions:** `PROBE` · `ADVANCE` · `STAY_ON_QUESTION` · `CLOSING` / wrap-up  
Also enforces probe limits and a safety turn ceiling (~28 turns).

**Say in viva:**  
“The LLM may propose probe or advance; DecisionEngine is the hard policy that caps probes and forces coverage-first progress.”

---

### CoverageEngine
**File:** `backend/dialogue/coverage_engine.py`

**What it is:** Tracks which **role blueprint domains** are covered, probe budgets, and follow-up limits.

**Why it matters:** Stops endless chatting. Interview completeness for Report V2 depends on coverage.

**Say in viva:**  
“CoverageEngine ensures each role domain is visited with a bounded probe budget—so the interview stays structured.”

---

### LLMAdapter
**File:** `backend/dialogue/llm_adapter.py`

**What it is:** Generates what the **AI interviewer says** (intro, domain question, follow-up wording, closing) via **Groq + Llama 3.3**.

**Not the same as Evaluator:** Adapter = spoken text · Evaluator = scores + adaptive suggestion.

**Say in viva:**  
“LLMAdapter writes interviewer speech; Evaluator grades candidate answers.”

---

### InterviewProcessor + VoiceTurnPolicy
**Files:**  
`backend/pipecat_integration/interview_processor.py`  
`backend/voice/voice_turn_policy.py`

**What they are:** Realtime voice glue. Decide when a spoken answer is “complete enough,” handle barge-in, silence nudges, echo timing, then call the dialogue adapter.

**Say in viva:**  
“InterviewProcessor sits in the Pipecat pipeline and decides when to hand speech transcripts to DialogueManager.”

---

### InterviewDialogueAdapter
**File:** `backend/integration/dialogue_adapter.py`

**What it is:** Thin bridge between Pipecat (voice) and SessionService/DialogueManager (logic). Keeps media code separate from interview policy.

**Say in viva:**  
“The adapter isolates voice I/O from dialogue logic so we can reuse the same brain on REST testing if needed.”

---

### Pipecat `interview_bot` (voice pipeline)
**File:** `backend/pipecat_integration/interview_bot.py`

**Pipeline order:**
```
WebSocket in → Silero VAD → Deepgram STT → InterviewProcessor → Cartesia TTS → WebSocket out
```

**Say in viva:**  
“interview_bot is the realtime process: audio in, VAD and STT, our processor, TTS out—dialogue stays behind the adapter.”

---

### RoleConfig / role blueprints
**Files:** `backend/core/role_registry.py`, `role_config.py`, `domain_packs.py`

**What they are:** Per-role interview blueprints (domains, seeds, limits). Recruiter picks a role; CoverageEngine uses that blueprint.

**Say in viva:**  
“Roles are blueprints of domains to cover—not just a label on the UI.”

---

### Report V2
**Folder:** `backend/reporting/` (`generator.py`, completion policy, HTML renderer, persistence)

**What it is:** Final structured feedback package (`REPORT_VERSION = "2.0"`): scores, domain ratings, narratives, completion type.

**Report types:** `complete` · `partial` · `incomplete` · `aborted`  
Complete ≈ wrap-up + enough scored turns + full coverage.

**Say in viva:**  
“Report V2 is honest labelling—we only mark complete when coverage and wrap-up conditions are met.”

---

### Recruiter dashboard + invites
**Folder:** `recruiter_dashboard/`  
**Candidate lobby:** `manual_client/` (invite resolve + pre-interview flow)

**What they are:** Recruiter creates invite tokens (optional email). Candidate opens invite, completes lobby instructions, clicks Ready, then voice interview starts. Dashboard browses saved reports; it does **not** run the interview engine.

**Say in viva:**  
“Invite is a role token and lobby gate; the interview engine starts only after Ready on the voice WebSocket.”

---

## 3. One full turn (memorize the flow)

1. Candidate speaks → browser sends audio to **:8765**  
2. **Silero VAD** detects speech end  
3. **Deepgram** returns transcript  
4. **InterviewProcessor** accepts the turn (debounce / barge-in / silence rules)  
5. **SessionService.process_turn** → **DialogueManager.handle_turn**  
6. **Guards** may redirect (no full score)  
7. Else **Evaluator** scores → **DecisionEngine** + **CoverageEngine** choose next action  
8. **LLMAdapter** may generate next question text  
9. **Cartesia TTS** speaks it back  
10. Context updated; later **Report V2** is built and saved for the recruiter  

---

## 4. Who owns what (for group division)

| Area | Core modules to know |
|------|----------------------|
| **AI / dialogue** | DialogueManager, Guards, DecisionEngine, CoverageEngine, Evaluator, LLMAdapter, InterviewContext |
| **Backend / realtime** | SessionService, interview_bot, InterviewProcessor, VoiceTurnPolicy, adapter, Report V2 |
| **Frontend** | Candidate lobby/voice UI (`manual_client`), recruiter dashboard pages |

---

## 5. Honest limits (say these if asked)

- **One** concurrent live voice session on the Pipecat bot (prototype scale)  
- Sessions are **in-memory** in the voice process (not multi-server ready)  
- **No** speech-emotion recognition or facial analysis  
- Behavioural signals = **text rubric** (clarity/confidence), not biometrics  
- Port **8000** = testing API only  
- Recruiter auth / file invites = demo-grade, not production SaaS  

---

## 6. Tiny glossary

| Term | Meaning |
|------|---------|
| **PROBE** | Ask a follow-up on the same domain (deepen answer) |
| **ADVANCE** | Move to the next blueprint domain |
| **Coverage** | How many role domains have been visited |
| **Barge-in** | Candidate interrupts the bot while it is speaking |
| **Report V2** | Structured final feedback format (version 2.0) |
| **Blueprint / role** | Planned set of interview domains for a job role |

---

## 7. Closing line for presentation

> “Our code separates concerns clearly: Pipecat handles realtime speech, SessionService manages sessions, DialogueManager runs each turn with guards and policy, DecisionEngine and CoverageEngine keep the interview structured, the Evaluator and LLMAdapter handle scoring and speech generation, and Report V2 delivers honest, structured feedback to the recruiter.”

---

*Share this file with the group. For full viva Q&A, also use `FYP_report/VIVA_TECHNICAL_QA.md`.*
