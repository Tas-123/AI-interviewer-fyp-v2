
# Context Management Architecture Review — This Project Only

**Core finding:** This system does **not** use a rolling chat `messages[]` memory. Context is a selective, in-process `InterviewContext` object. Every Groq call is a **fresh 2-message request** (fixed system + one constructed user prompt). Full answer history is stored for reports/guards; it is **not** replayed as conversation history to the question LLM.

There is **no** job description document, **no** Redis, **no** vector DB, and **no** conversation summarizer/trimmer.

---

## PART 1 — REQUEST FLOW (one voice turn)

```

Candidate speaks

  → Mic PCM over WebSocket (manual_client / pipecat transport)

  → Deepgram STT (pipeline in interview_[bot.py](http://bot.py))

  → InterimTranscriptionFrame / TranscriptionFrame

  → InterviewProcessor.process_frame()

  → *merge*transcript_part()  (buffer STT)

  → *schedule*turn_debounce() / VAD stop

  → *process*buffered_transcript_after_delay()

  → *prepare*transcript_for_turn()  (gate/clean/tail suppress)

  → *submit*turn(user_text)

       ├─ ConversationEventPublisher.message(role=user)   # UI only

       ├─ adapter.process_user_text(session_id, user_text)

       │     → SessionService.process_turn()

       │     → DialogueManager.handle_turn(transcript)

       │           ├─ prepare_transcript_for_evaluation()

       │           ├─ [GuardPipeline.run](http://GuardPipeline.run)(GuardContext)

       │           ├─ Evaluator.adaptive_evaluate(...)     # LLM #1 (eval+follow-up)

       │           ├─ DecisionEngine.decide_from_adaptive()

       │           ├─ [optional] LLMAdapter.generate()     # LLM #2 (next domain Q)

       │           └─ InterviewContext.add_turn / add_evaluation

       └─ *speak*to_client() → TTSSpeakFrame → Cartesia TTS → client audio

```

| Step | File | Function | What it does |

|------|------|----------|--------------|

| WS connect / start | `backend/pipecat_integration/interview_bot.py` | `on_client_connected` | Calls `adapter.start_interview(**start_payload)` with `resume_text` / `target_role` |

| STT frames | `interview_processor.py` | `process_frame` | Merges interim/final STT; schedules debounce |

| Gate text | `interview_processor.py` | `_prepare_transcript_for_turn` | Echo/filler/tail filters; clears buffer |

| Submit | `interview_processor.py` | `_submit_turn` | UI event + `adapter.process_user_text` + TTS |

| Adapter | `backend/integration/dialogue_adapter.py` | `process_user_text` | Thin bridge to `SessionService` |

| Session | `backend/core/session_service.py` | `process_turn` | Looks up `DialogueManager` by `session_id` |

| Dialogue | `backend/dialogue/dialogue_manager.py` | `handle_turn` | Guards → evaluate → decide → generate → store |

| Eval LLM | `backend/dialogue/evaluator.py` | `adaptive_evaluate` → `_run_primary_adaptive` | Scores answer + proposes `next_question` |

| Policy | `backend/dialogue/decision_engine.py` | `decide_from_adaptive` | Probe budgets / ADVANCE / CLOSING |

| Question LLM | `backend/dialogue/llm_adapter.py` | `generate` | Only when engine needs a new domain question |

| TTS | `interview_processor.py` | `_speak_to_client` | Chat bubble + `TTSSpeakFrame` |

**Note:** There is no `process_user_message()` in this codebase. The voice entrypoint is `_submit_turn` → `process_user_text`.

---

## PART 2 — CONTEXT CONSTRUCTION

### Where the final prompt is built

Two different LLM call sites build prompts:

1. **Adaptive evaluation** (every scored turn)  

   `backend/dialogue/evaluator.py` → `_run_primary_adaptive()`  

   fills `ADAPTIVE_EVALUATION_PROMPT` from `backend/dialogue/prompts.py`

2. **Question generation** (intro / advance to new domain / legacy follow-up)  

   `backend/dialogue/llm_adapter.py` → `_generate_intro` / `_generate_technical` / `_generate_behavioral` / `_generate_followup` → `_call_llm`

### System prompt — where it comes from

| Layer | Source |

|-------|--------|

| Persona rules | `backend/core/interviewer_policy.py` → `INTERVIEWER_PERSONA_RULES` |

| Assembled templates | `backend/dialogue/prompts.py` → `INTERVIEWER_PERSONA_SYSTEM_PROMPT`, `TECHNICAL_SYSTEM_PROMPT`, etc. |

| Groq API “system” role | Hardcoded short string inside `LLMAdapter._call_llm` and `Evaluator._call_groq` |

```python

# backend/dialogue/llm_[adapter.py](http://adapter.py) — *call*llm

messages=[

    {

        "role": "system",

        "content": (

            "You are a professional live voice interviewer. "

            "Never coach, hint, or provide example answers. "

            "Return only the spoken response. No markdown, no bullets, no headings."

        ),

    },

    {"role": "user", "content": prompt},

]

```

The long interviewer rules live in the **user** prompt body (via `TECHNICAL_SYSTEM_PROMPT` etc.), not as a multi-turn system chat.

### Resume — where inserted

| Stage | File | Function |

|-------|------|----------|

| Parse / normalize | `backend/dialogue/session_bootstrap.py` | `bootstrap_from_request` / `CandidateProfile.to_resume_data` |

| Store | `backend/dialogue/context.py` | `InterviewContext.__init__(resume_data)` |

| Inject into greeting | `llm_adapter.py` | `_generate_intro` — skills, experience, name, role, profile_source |

| Resume questions | `dialogue_manager.py` | `_init_question_selector` → `QuestionSelector.set_resume_questions` |

```python

# backend/dialogue/llm_[adapter.py](http://adapter.py) — *generate*intro

skills_str = ", ".join(context.skills) if context.skills else "general"

experience = context.resume_data.get("experience", "not specified")

prompt = INTRO_SYSTEM_PROMPT.format(

    skills=skills_str,

    experience=experience,

)

```

### Job description

**Does not exist in this implementation.**  

No `job_description` field anywhere in backend Python. Role structure comes from `target_role` + `role_registry` / `INTERVIEW_BLUEPRINT`, not a JD document.

### Previous interview messages

Stored as two parallel lists on `InterviewContext`:

```python

# backend/dialogue/[context.py](http://context.py) — InterviewContext.__init__

self.question_history = []

self.transcript_history = []

```

Written by `InterviewContext.add_turn(question, transcript)`.

### Assistant responses

Stored in `question_history` (the next spoken question).  

UI also emits assistant text via `ConversationEventPublisher` — **not** fed back into LLM prompts.

### Evaluation notes

Stored in `InterviewContext.evaluations` via `add_evaluation()`.  

Compact summary for the next adaptive call:

```python

# backend/dialogue/[context.py](http://context.py) — get_previous_evaluations_summary

summaries.append({

    "turn": i + 1,

    "overall_score": ev.get("overall_score", 0),

    "weakest_dimension": ev.get("weakest_dimension", "unknown"),

    "hire_signal": ev.get("hire_signal", "N/A"),

})

```

Full rubrics / adaptive traces go to reports `adaptive_trace`), not into question-generation prompts.

### Follow-up instructions

- Style rules embedded in `ADAPTIVE_EVALUATION_PROMPT` / `FOLLOWUP_SYSTEM_PROMPT` / `WEAKNESS_FOLLOWUP_PROMPT` `prompts.py`)

- Probe budgets in `CoverageEngine` + `DecisionEngine.decide_from_adaptive`

- Actual follow-up text usually comes from evaluator `decision.next_question` (not from replaying chat history)

---

## PART 3 — CONTEXT WINDOW (what is sent every turn)

### Exact structure of a Groq call

Always:

```text

messages = [

  { role: "system", content: "<short fixed persona>" },

  { role: "user",   content: "<one big constructed prompt>" }

]

```

**Not sent:** accumulating chat history, full transcript list, DB rows, Redis, vector memory.

### Adaptive evaluation call (main path)

Built in `Evaluator._run_primary_adaptive`:

| Input | Included? |

|-------|-----------|

| System prompt (short evaluator) | Yes |

| Current question | Yes |

| Current candidate answer | Yes |

| Compact previous_evaluations | Yes (scores only) |

| interview_stage (EARLY/MID/LATE) | Yes |

| STT noisy note | Sometimes |

| Full conversation | **No** |

| Full transcript_history | **No** |

| Resume text | **No** |

| Job description | **No** (N/A) |

| Question history list | **No** (only current Q) |

### Question generation call `LLMAdapter`)

| Call type | What’s in the user prompt |

|-----------|---------------------------|

| Intro | Resume skills/experience/name/role |

| Technical (static bank) | Often **no LLM** — hardcoded domain question + naturalize |

| Technical (LLM fallback) | Domain policy + **previous questions only** via `_build_history_text` |

| Behavioral | Category + previous questions only |

| Follow-up via LLMAdapter | Topic/difficulty + policy — **no answer text, no history** |

```python

# backend/dialogue/llm_[adapter.py](http://adapter.py) — *build*history_text

def *build*history_text(self, context):

    """Build a text summary of previously asked questions."""

    if not context.question_history:

        return ""

    lines = []

    for i, q in enumerate(context.question_history, 1):

        lines.append(f"{i}. {q}")

    return "\n".join(lines)

```

**Critical asymmetry:** Question LLM sees prior **questions**. Adaptive evaluator sees current **Q+A** + compact prior **scores**. Prior **answers** are not injected into question-generation prompts.

---

## PART 4 — MEMORY (every place it exists)

| Memory type | Location | Affects LLM? |

|-------------|----------|--------------|

| **Conversation memory (Q/A lists)** | `InterviewContext.question_history`, `transcript_history` | Partially — questions → LLMAdapter; answers → adaptive call only for *current* turn |

| **Session memory (in-process)** | `SessionService._sessions: dict[str, InterviewSession]` | Indirect (owns DialogueManager) |

| **Coverage / probe budgets** | `CoverageEngine` on context | Policy only (which path), not prompt text |

| **Evaluations** | `context.evaluations` + compact summary | Yes — adaptive prompt |

| **Adaptive trace** | `context.adaptive_trace` | Report only |

| **Resume profile** | `context.resume_data` | Intro + question selector |

| **Postgres** | `backend/dialogue/database.py` `save_session` / `save_response` | **No** for runtime LLM (write-side persistence) |

| **Redis** | **Does not exist** | — |

| **Vector DB / embeddings** | **Does not exist** (dedup uses `difflib` in `question_dedup.py`) | — |

| **UI conversation events** | `ConversationEventPublisher` | **No** |

| **Voice processor locals** | `latest_user_transcript`, resume-window state | Gates text into dialogue only |

| **Legacy voice modules** | `voice/voice_session_manager.py`, `conversation_orchestrator.py` | Parallel/older path; live Pipecat path uses SessionService |

What actually shapes LLM behavior: **InterviewContext fields selectively copied into per-call prompts**, plus static templates in `prompts.py`.

---

## PART 5 — CONTEXT LIMITS (60-minute interview)

**What happens:** The project does **not** time-limit by minutes. It limits by **turn/domain coverage**.

```python

# backend/dialogue/decision_[engine.py](http://engine.py) — *safety*ceiling_reached

# uses context.max_total_interview_turns (from policy, currently 28)

```

`MAX_TOTAL_INTERVIEW_TURNS = 28` in `backend/core/interviewer_policy.py`.

| Behavior | Present? |

|----------|----------|

| Trim messages | **No** |

| Summarize conversation | **No** |

| Forget old answers | **No** (kept in RAM forever for session) |

| Compress history | **No** |

| Wrap on turn ceiling | **Yes** — force CLOSING |

| Wrap when all domains covered | **Yes** — coverage-first policy |

At 60 minutes with many turns: `question_history` grows unbounded in RAM; `_build_history_text` dumps **all prior questions** into the technical/behavioral prompt → token growth, but answers are still not fully replayed. Adaptive eval prompt grows with compact eval summaries (one small object per scored turn).

---

## PART 6 — TOKEN USAGE

| Capability | Status | Where |

|------------|--------|-------|

| Calculate tokens (tiktoken etc.) | **Does not exist** | — |

| Estimate context size | **Does not exist** | — |

| Log prompt length | **Does not exist** (latency is logged for adaptive) | `evaluator.py` latency_ms |

| `max_output_tokens` | **Yes** | `LLMAdapter._call_llm` → `max_tokens=180`; `Evaluator._call_groq` → `700` JSON / `220` text; guards `6080120` |

| Prevent context overflow | **No** dedicated guard | Only structural caps (turn ceiling, compact evals, question-only history) |

---

## PART 7 — FOLLOW-UP QUESTIONS

### Responsible code

| Role | File | Function |

|------|------|----------|

| Generate follow-up text | `evaluator.py` | `_run_primary_adaptive` → JSON `decision.next_question` |

| Gate probe vs advance | `decision_engine.py` | `_decide_from_adaptive_impl` |

| Use evaluator question | `dialogue_manager.py` | `handle_turn` (PROBE path uses `decision.get("next_question")`) |

| Legacy weakness follow-up | `evaluator.py` | `generate_weakness_followup` + `WEAKNESS_FOLLOWUP_PROMPT` |

| Labeling for reports | `followup_policy.py` | `classify_followup_type` |

### How the LLM knows previous answers

For the **adaptive evaluator** (where follow-ups are born):

- **Explicitly injects** current question + current answer  

- Injects **compact previous evaluation scores**, not prior answer text  

- Does **not** rely on multi-turn conversation history

For **LLMAdapter._generate_followup** (legacy path):

- Injects topic/difficulty only  

- **Does not** inject the previous answer (despite the prompt saying “based on the candidate's weak answer”)

So answer-aware follow-ups in the live path come from the **evaluator seeing the current answer in the same call**, not from a stored chat thread.

---

## PART 8 — PROMPT BUILDER

Templates live in `backend/dialogue/prompts.py` (not a separate PromptBuilder class).

### Sections of `ADAPTIVE_EVALUATION_PROMPT` (main dynamic prompt)

| Section | Changes every turn? |

|---------|---------------------|

| Technical follow-up style rules | Static |

| Evaluator persona / tasks | Static |

| Scoring rubric / calibration | Static |

| `{current_question}` | Dynamic |

| `{candidate_answer}` | Dynamic |

| `{previous_evaluations}` | Dynamic (grows) |

| `{interview_stage}` | Dynamic (EARLY/MID/LATE by turn_count) |

| Optional STT quality note | Dynamic when noisy |

### Question prompts `TECHNICAL_SYSTEM_PROMPT` etc.)

| Part | Stability |

|------|-----------|

| Persona + voice rules | Static |

| `{topic}` / `{difficulty}` | Per action |

| Interview policy appendix (role, domain) | Per turn |

| Previous questions list | Grows every turn |

| Resume skills (intro only) | Session-constant |

Many domain advances **skip the LLM entirely** and use the hardcoded bank in `LLMAdapter._generate_technical` — so prompt construction often never runs for primary domain questions.

---

## PART 9 — ENGINEERING REVIEW

### What is good

1. **Selective context** — not dumping full chat into every call; reduces waste vs naive chatbots.  

2. **Single state object** — `InterviewContext` is clear and inspectable.  

3. **Separation of concerns** — voice gating `InterviewProcessor`) vs dialogue `DialogueManager`) vs policy `DecisionEngine`) vs prompts `prompts.py`).  

4. **Compact eval summaries** — scores only, not full rubrics, in adaptive prompts.  

5. **Coverage/probe budgets** — structure interviews without relying on the LLM to remember domains.  

6. **Static domain question bank** — predictable coverage, fewer tokens, less hallucination.

### What is bad / risky

1. **Asymmetric memory** — follow-ups often lack prior answers in question-gen path; evaluator only sees *current* answer. Cross-turn “you said earlier…” continuity is weak.  

2. *`_generate_followup` ignores answer** — policy text claims awareness it doesn’t receive.  

3. **No job description** — role is hardcoded blueprint, not JD-conditioned.  

4. **No context window management** — `question_history` can grow without summarization.  

5. **Dual LLM calls per turn** (adaptive + sometimes generate) — latency/cost.  

6. **In-process session store only** — process restart loses live memory; Postgres is not read back into LLM context.  

7. **Huge static prompt bodies** repeated every adaptive call — constant token waste.  

8. **UI conversation stream ≠ LLM memory** — easy to confuse when debugging “why didn’t it remember?”

### Bottlenecks

- Adaptive JSON call `max_tokens=700`) every scored turn  

- Growing `Previous questions asked…` block in technical/behavioral LLM prompts  

- Guard LLM calls (intent/relevance) add more short prompts under load  

### Long-interview failure modes

- At ~28 turns, forced close (by design) — not a 60-minute soft limit  

- Before that: larger prompts, higher Groq cost, possible truncation by **provider** context limit (unhandled in code)  

- RAM growth of `transcript_history` + `adaptive_trace` (report size, not usually LLM)

### Where tokens are wasted

- Repeating long `ADAPTIVE_EVALUATION_PROMPT` scaffolding every turn  

- Injecting **all** prior questions when a last-N window would suffice  

- Calling question LLM when static bank already has the domain question (partially mitigated)  

- Rethink pass in evaluation pipeline (when enabled) doubles eval tokens

---

## PART 10 — IMPROVEMENTS (specific to this codebase)

1. *`llm_adapter.py` `_generate_followup`**  

   Inject `context.transcript_history[-1]` and `question_history[-1]` into the prompt, or delete this path and always use evaluator `next_question`.

2. *`llm_adapter.py` `_build_history_text`**  

   Change from full list → last 5–8 questions, or domain-filtered questions only.

3. *`evaluator.py` / `prompts.py`**  

   Split `ADAPTIVE_EVALUATION_PROMPT` into a short cached system prompt + small user payload `question`, `answer`, `prev_evals`, `stage`) to cut repeated rubric tokens.

4. *`context.py`**  

   Add `get_answer_aware_snippets(n=2)` (last N Q/A pairs) and pass into adaptive prompt for cross-turn continuity without full history.

5. *`session_service.py`**  

   Document clearly that Postgres is persistence-only; if multi-worker is needed later, hydrate `InterviewContext` from DB or introduce Redis session store (currently explicitly out of scope).

6. *`decision_engine.py` + `dialogue_manager.py`**  

   Prefer static bank + evaluator follow-up; avoid second `LLMAdapter.generate` call unless bank miss / duplicate.

7. **New thin `PromptAssembler` module** (extract from `llm_adapter.py` + `evaluator.py`)  

   Single place to log `len(prompt)`, estimate tokens, assert budget.

8. **Do not add a full chat messages[] history** without a summarizer — it would break the current turn-budget design and explode cost.

---

## PART 11 — VISUALIZATION

```

┌─────────────────── VOICE LAYER ───────────────────┐

│  Mic → WS → Deepgram STT                          │

│       → InterviewProcessor (buffer/debounce/tail) │

│       → ConversationEventPublisher (UI only) ──────┼──► Browser chat

│       → TTSSpeakFrame → Cartesia TTS              │

└───────────────────────┬───────────────────────────┘

                        │ user_text + session_id

                        ▼

┌─────────────────── SESSION LAYER ─────────────────┐

│  InterviewDialogueAdapter.process_user_text       │

│  SessionService._sessions[session_id]             │

│       └── DialogueManager                         │

│             └── InterviewContext  ◄── STATE OF     │

│                   question_history                  │    RECORD

│                   transcript_history                │

│                   evaluations / coverage / resume   │

└───────────────────────┬───────────────────────────┘

                        │

          ┌─────────────┴─────────────┐

          ▼                           ▼

┌─────────────────┐         ┌──────────────────────┐

│ GuardPipeline   │         │ Evaluator            │

│ (may short-LLM) │         │ *run*primary_adaptive│

└─────────────────┘         │ PROMPT =             │

                            │  static rubric       │

                            │  + current Q/A       │

                            │  + compact evals      │

                            │  + stage             │

                            └──────────┬───────────┘

                                       │ [decision.next](http://decision.next)_question

                                       ▼

                            ┌──────────────────────┐

                            │ DecisionEngine       │

                            │ probe / advance /    │

                            │ close (coverage)     │

                            └──────────┬───────────┘

                                       │

                    ┌──────────────────┼──────────────────┐

                    ▼                                     ▼

         Use evaluator next_question          LLMAdapter.generate

         (PROBE)                              (new domain ask)

                                              PROMPT =

                                                persona + domain

                                                + previous QUESTIONS

                                                (+ resume on intro)

```

**What each component contributes to the final LLM prompt:**

```

[prompts.py](http://prompts.py) ─────────── static persona / rubric / style

resume_data ────────── intro only (skills/experience)

question_history ───── LLMAdapter history text (questions only)

transcript (current) ─ Evaluator candidate_answer

evaluations summary ── Evaluator previous_evaluations

CoverageEngine ─────── chooses path (not prompt text)

DB / UI events ─────── nothing to LLM

```

---

## PART 12 — CODE REFERENCE INDEX

| Concern | Path | Class / Function |

|---------|------|------------------|

| Voice turn submit | `pipecat_integration/interview_processor.py` | `_submit_turn` |

| STT buffering | same | `process_frame`, `_merge_transcript_part`, `_prepare_transcript_for_turn` |

| Adapter | `integration/dialogue_adapter.py` | `process_user_text` |

| Session store | `core/session_service.py` | `SessionService`, `InterviewSession` |

| Turn orchestration | `dialogue/dialogue_manager.py` | `handle_turn` |

| State of record | `dialogue/context.py` | `InterviewContext`, `add_turn`, `get_previous_evaluations_summary` |

| Prompt templates | `dialogue/prompts.py` | `ADAPTIVE_EVALUATION_PROMPT`, `TECHNICAL_SYSTEM_PROMPT`, … |

| Question LLM | `dialogue/llm_adapter.py` | `generate`, `_build_history_text`, `_call_llm` |

| Eval LLM | `dialogue/evaluator.py` | `adaptive_evaluate`, `_run_primary_adaptive`, `_call_groq` |

| Follow-up policy | `dialogue/decision_engine.py` | `decide_from_adaptive` |

| Resume bootstrap | `dialogue/session_bootstrap.py` | `CandidateProfile`, `bootstrap_from_request` |

| Persona rules | `core/interviewer_policy.py` | `INTERVIEWER_PERSONA_RULES`, `MAX_TOTAL_INTERVIEW_TURNS` |

| UI events (not LLM) | `pipecat_integration/conversation/publisher.py` | `ConversationEventPublisher` |

| DB (not LLM) | `dialogue/database.py` | `save_session`, `save_response` |

### Explicitly absent

| Feature | Verdict |

|---------|---------|

| Job description injection | **Does not exist** |

| Redis / shared session cache | **Does not exist** |

| Vector DB / embeddings memory | **Does not exist** |

| Conversation summarizer / trimmer | **Does not exist** |

| Token counting / overflow guard | **Does not exist** |

| Multi-turn Groq `messages` history | **Does not exist** (always 2-message calls) |

| `process_user_message()` | **Does not exist** (use `_submit_turn` / `process_user_text`) |

---

**Bottom line:** Context in this project is an **engineered state machine** `InterviewContext` + coverage budgets), not a chatbot memory. The LLM is given a **reconstructed snapshot** each call—current answer for scoring/follow-ups, prior questions for anti-repeat, resume for intro, compact scores for calibration—rather than the full interview transcript.

```

To save it into `docs/`, switch to Agent mode and ask me to write `docs/CONTEXT_MANAGEMENT_ARCHITECTURE.md`.