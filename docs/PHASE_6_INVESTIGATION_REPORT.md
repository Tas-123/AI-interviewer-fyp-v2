# Phase 6 Investigation Report — Interview Quality & Voice Experience

**Status:** Analysis only — **no code changes**  
**Scope:** Phase 6 (Interview Quality & Voice Experience)  
**Date:** 2026-07-08  
**Branch analyzed:** `uthman` (post Phase 6A–6C + voice hotfix)  
**TTS provider in use:** **Cartesia** (not ElevenLabs / OpenAI)  
**LLM provider in use:** **Groq** (`llama-3.3-70b-versatile`)

---

## Executive Summary

Live interviews currently feel **robotic**, can **hang forever on silence**, occasionally **chop TTS mid-sentence**, sometimes **repeat questions**, and frequently log **duplicated transcripts**. These are not one root cause — they are the combined result of:

1. **Template-heavy interviewer speech** (fixed domain bank + rigid guard redirects)  
2. **A fully reactive voice loop with no candidate silence timeout**  
3. **WAV-per-chunk Cartesia streaming + client play scheduling / barge-in discard**  
4. **Incomplete dedup on the PROBE path** (evaluator follow-ups bypass uniqueness)  
5. **Deepgram interim + VAD-fragment merge** that reconstructs progressive STT text  

None of these require a Phase 7 redesign. All sit inside Phase 6 quality/voice work. Architecture remains sound (Pipecat → processor → SessionService → DialogueManager → Cartesia). Most fixes are **implementation / policy**, not structural.

| Issue | Priority | Complexity | Architecture change? |
|-------|----------|------------|----------------------|
| 1. Robotic conversation | High | Medium | No — prompts + templates |
| 2. Infinite silence wait | **Critical** | Medium | Minor — add silence policy |
| 3. Mid-question TTS pauses | High | Medium–High | Possibly transport/TTS config |
| 4. Duplicate questions | High | Low–Medium | No — close PROBE dedup hole |
| 5. Transcript repetition | High | Medium | No — merge/cleanup |
| 6. Pipeline bottlenecks | Medium | Medium | No — timing / races |

**Recommended implementation order (when approved):**

1. Candidate silence / no-answer timeout (Critical)  
2. PROBE-path question uniqueness + redirect variety (High)  
3. Transcript merge / progressive interim collapse (High)  
4. TTS/streaming gap mitigation (High)  
5. Natural phrasing layer for bank + acknowledgements (High)  
6. Debounce / race cleanup and dead-code notes (Medium)

---

## Findings

### Finding A — Interviewer speech is mostly templates, not conversation

**What happens:** Almost every domain advance starts with the same family of phrases (`Let's talk about…`, `Now let's…`, `Let's move to…`). Guard hits speak nearly identical lines (`Sure, I'll repeat…`, `Let's stay focused…`, `Please answer this directly…`). Acknowledgements from follow-up prompts cluster on `Got it.` / `Understood.`

**Where:**

| Layer | File | Behavior |
|-------|------|----------|
| Persona | `backend/core/interviewer_policy.py` | Strict interviewer rules (good for fairness) |
| Prompts | `backend/dialogue/prompts.py` | Asks for natural speech, but also templates acknowledgement style |
| Bank + naturalize | `backend/dialogue/llm_adapter.py` → `_naturalize_static_question()` | Fixed rewrites per domain |
| Guards | `intent_guard.py`, `domain_guard.py`, `meta_conversation_guard.py`, `echo_guard.py` | Hard-coded redirect strings |
| PROBE text | `dialogue_manager.py` + `evaluator.py` | Evaluator `next_question` spoken as-is |

**Why it feels robotic:**

- Domain **primary** questions are taken from a deterministic bank, then lightly rewritten by `_naturalize_static_question()` — nine of ten domains use the same rhetorical frame.
- Soft “Voice-Mode Spoken Rules” in prompts do not override hard-coded bank/guard text.
- Professional-over-coach persona suppresses warmth without providing an alternate acknowledgement corpus.
- Guard redirects (by design) restating the same question sound like the bot is stuck in a loop.

**Expected:** Varied transitions (“Building on that…”, “Shifting topics…”, “Alright — one more technical angle…”), soft acknowledgements tied to the answer, and redirects that do not re-read the entire question every time.

**Recommended solution (later):**

1. Expand acknowledgement / transition phrase banks with rotation (no fixed prefix every turn).  
2. Soften guard redirects: short cue + abbreviated core question (`short_repeat_question` already exists — use it more consistently).  
3. Optional second LLM “speakable phrasing” pass **only for delivery** (keep bank intent fixed for coverage fairness).  
4. Cap acknowledgement to ~3–5 token prefixes; ban stacking of “Please answer this directly” after the first redirect.

---

### Finding B — No candidate silence / no-answer timeout (Critical)

**What happens:** After the bot finishes a question, if the candidate is silent (or mic muted / ambient too quiet for VAD+Deepgram finals), the pipeline **waits indefinitely**. Nothing prompts, rephrases, or moves on.

**Current logic:**

| Mechanism | Exists? | Role |
|-----------|---------|------|
| Deepgram `endpointing` (~500 ms) | Yes | Ends utterance *after* speech; not a no-speech timer |
| VAD `audio_idle_timeout=2.0` | Yes | Helps end speech already started |
| Interim silence fallback 1.4 s | Yes | Only if **interim text already exists** |
| Transcript debounce 3.0 s | Yes | After transcript, not for empty silence |
| Short-answer grace 2.5 s | Yes | After short speech |
| Candidate no-answer timer after bot stopped speaking | **No** | — |
| `PipelineTask(idle_timeout_secs=None)` | Yes | Intentionally disables *pipeline idle shutdown*, not candidate prompt |

`DialogueManager` is **turn-driven**: `handle_turn(transcript)` never runs without text. There is no scheduled “bot stopped speaking → N seconds of quiet → nudging TTS”.

**Why:** Design assumed a reactive STT loop. Phase 6 voice hotfix improved *capture*, not *absence of speech*. Mic-off case presents as silence forever — matching reported UX.

**Expected (industry pattern):**

1. Soft nudge at ~6–8 s (“Take your time — whenever you’re ready.”)  
2. Rephrase / repeat at ~12–15 s  
3. Optional skip / next domain at ~20–25 s or after second silence  

**Recommended solution (later):**

- Add `candidate_silence_timeout_seconds` + `candidate_silence_nudge_seconds` to `VoiceTurnPolicy` / config.  
- In `InterviewProcessor`, on `BotStoppedSpeakingFrame`, start an async timer; cancel on any user speech / interim / final.  
- On timeout, push a `TTSSpeakFrame` nudge or call adapter with a synthetic meta event (`SILENCE_TIMEOUT`) that Meta/Idk policies already understand.

**Complexity:** Medium · **Risk:** Medium (false nudges if VAD misses quiet speech) · **Architecture:** Implementation only (small policy addition)

---

### Finding C — Mid-question audio gaps (Cartesia + WAV chunking + client)

**What happens:** Candidate hears “Tell me about…” then a multi-second pause, then the rest of the question.

**Providers:** Cartesia TTS (not ElevenLabs/OpenAI). Confirmed in `interview_bot.py` + `.env.example`.

**Contributing causes (ranked):**

1. **WAV-header-per-chunk transport**  
   `WebsocketServerParams(add_wav_header=True)` + client `decodeAudioData` on every Blob. Each chunk is a tiny WAV (~0.04 s). Jitter / decode delay between chunks produces audible gaps if the play queue drains.

2. **Client barge-in discard race**  
   `client.js` discards bot audio for `BARGE_IN_DISCARD_BOT_AUDIO_MS` after client RMS spikes. False barge-in mid-question mutes the rest of TTS while the server keeps streaming — perceived as “audio stopped midway” then resumes if discard window ends while chunks continue (or sounds broken if queue cleared).

3. **Cartesia context force-complete** (observed in prior live logs)  
   Overlapping / double `TTSSpeakFrame` (e.g. closing said twice) caused Cartesia to force-complete remaining text — related pattern for interruption of in-flight contexts.

4. **Late TTS start ≠ mid-sentence gap**  
   Groq `asyncio.to_thread` (eval + generate) delays *start* of speech after user answer. That feels like dead air between turns, not a mid-utterance cut. Distinct from issue C but worsens “awkward silence” overall.

5. **Server interrupt incomplete historically**  
   Hotfix added `request_client_interrupt`; residual timing where client drops audio while Cartesia continues still explains uneven playback.

**Expected:** Continuous question audio with ≤ ~50–100 ms inter-chunk gaps; barge-in only on sustained genuine speech.

**Recommended solution (later):**

1. Evaluate `add_wav_header=False` + raw PCM scheduling (or larger TTS frames).  
2. Raise client barge RMS / min frames; do not discard after bot *started* until min speak window.  
3. Guarantee **one** TTSSpeakFrame per turn (already known duplicate closing).  
4. Optionally pre-buffer more than 0.15 s jitter for long questions.

**Complexity:** Medium–High · **Risk:** Medium (transport changes need careful retest) · **Architecture:** Mostly implementation; may touch transport params

---

### Finding D — Duplicate / near-duplicate questions

**What happens:** Same topic or very similar wording is asked again later (or immediately after a redirect / probe).

**Current behavior:**

| Path | Dedup applied? |
|------|----------------|
| ADVANCE / `type=="ask"` via `LLMAdapter` + `_ensure_unique_question` | Yes |
| Domain skip after `domain_primary_already_asked` | Yes |
| **PROBE** branch: `question = decision.get("next_question")` | **No `_ensure_unique_question`** |
| Guard repeats / IDK rephrase / clarification | Intentional restatement (feels duplicate) |
| Similarity threshold `0.82` | Misses paraphrases humans hear as same |

**Root cause (primary):** In `dialogue_manager.py`, when the DecisionEngine allows a PROBE, the evaluator’s `next_question` is used **directly** without `_ensure_unique_question()`. ADVANCE forces uniqueness; PROBE does not.

Secondary causes:

- Redirect stacking (pre-hotfix) made repeats longer; core still re-asks by design.  
- Fixed bank means returning to a domain (or wording clash between follow-up and later bank question) can sound identical.  
- Meta “move on” vs domain redirect disagreement historically looped the same question (addressed partially by SKIP_REQUEST — still worth validating).

**Expected:** Within one session, no question above ~0.75–0.80 similarity to history except explicit “repeat please”; probes must vary wording.

**Recommended solution (later):**

1. Always pass PROBE and weakness follow-ups through `_ensure_unique_question`.  
2. Feed last N answers into PROBE generation so follow-ups reference specifics.  
3. Treat “repeat” intents separately from accidental duplicates.  
4. Slightly lower similarity threshold or add fingerprint of domain+intent.

**Complexity:** Low–Medium · **Risk:** Low · **Architecture:** Implementation

---

### Finding E — Transcript repetition in logs / evaluation text

**What happens:** Logs show progressive copies:

```text
My name is…
My name is Muhammad Usman…
My name is Muhammad Usman…
```

**Pipeline:**

```text
Deepgram interim (growing) → Buffered interim logs
Deepgram finals (VAD stop/start fragments) → _merge_transcript_part
clean_live_transcript → DialogueManager
```

**Root causes:**

1. **Deepgram** correctly emits progressive interims — logging every interim makes logs look “repetitive” even when designed that way.  
2. **VAD `SPEAKING ↔ STOPPING` flips** emit multiple short finals; merge **appends** when neither string contains the other → duplicated phrases.  
3. **`_merge_transcript_part`** improved with overlap trimming / `_prefer_longest_overlapping_segment`, but progressive extensions that share prefixes without exact n-gram repeats still concatenate.  
4. Cleanup runs **after** merge; if merge already blended three versions, cleaner cannot always recover human meaning.

**Expected:** One coherent utterance per turn; logs may still show interim growth at DEBUG only.

**Recommended solution (later):**

1. Prefer latest interim as source of truth when it **extends** prior (prefix relation), do not append.  
2. On final, if new final is nearly a suffix/extension of buffer, replace rather than append.  
3. Log interims at DEBUG; INFO only finals / cleaned.  
4. Further raise VAD `stop_secs` if needed after silence timer lands.

**Complexity:** Medium · **Risk:** Medium (over-aggressive merge can drop words) · **Architecture:** Implementation

---

### Finding F — Overall voice pipeline diagnostics

```text
Mic (+gain) → WS PCM → Silero VAD → Deepgram STT
  → InterviewProcessor (merge, debounce, grace)
  → asyncio.to_thread(DialogueAdapter → SessionService → DialogueManager
       → Guards → Groq eval → Decision → Groq/bank question)
  → Cartesia TTS → WS WAV chunks → Browser AudioContext queue
```

| Concern | Severity | Notes |
|---------|----------|-------|
| Serial Groq (eval then maybe generate) | Medium | Dominant turn latency |
| Debounce 3.0 + grace 2.5 | Medium | Feels sluggish; necessary for STT noise |
| No silence policy | Critical | Finding B |
| Interim finalize vs debounce races | Medium | Parallel tasks; cancel logic present but subtle |
| Single-client WS | Low for FYP | Scalability note only |
| Duplicate closing TTS | Low | Two frames on complete |
| Client barge-in vs server TTS | High | Finding C |

---

## Root Cause Analysis (Per Issue Template)

### 1. Human-like Conversation

| Field | Detail |
|-------|--------|
| **Root cause** | Deterministic domain bank + rigid naturalize prefixes + hard-coded guard strings dominate spoken output; prompts request “natural” speech but do not control templates |
| **Files** | `prompts.py`, `llm_adapter.py`, `interviewer_policy.py`, `intent_guard.py`, `domain_guard.py`, `meta_conversation_guard.py`, `echo_guard.py`, `evaluator.py` |
| **Modules** | LLMAdapter, GuardPipeline, Evaluator PROBE text |
| **Current** | Same transition patterns; scripted acknowledgements; repeated redirect wording |
| **Expected** | Varied transitions, short answer-aware acknowledgements, shorter redirects |
| **Why** | Fairness/coverage favored fixed questions; conversational phrasing never layered on top |
| **Solution** | Phrase banks + optional speakable rewrite pass; soften redirects |
| **Complexity** | Medium |
| **Risk** | Low–Medium (phrasing drift vs coverage) |
| **Architecture?** | No |

### 2. Silence Handling

| Field | Detail |
|-------|--------|
| **Root cause** | No post-bot-speech candidate silence timer; DM is transcript-reactive only |
| **Files** | `interview_processor.py`, `interview_bot.py`, `voice_turn_policy.py`, `core/config.py`, `dialogue_manager.py` |
| **Modules** | InterviewProcessor, VoiceTurnPolicy, PipelineTask |
| **Current** | Wait forever if no STT final / interim |
| **Expected** | Nudge → rephrase → skip after staged timeouts |
| **Why** | Omitted feature; idle_timeout only prevents pipeline suicide |
| **Solution** | Timer on BotStoppedSpeaking; synthetic silence events |
| **Complexity** | Medium |
| **Risk** | Medium (false nudges) |
| **Architecture?** | Small policy addition only |

### 3. Question Audio Stops Midway

| Field | Detail |
|-------|--------|
| **Root cause** | Compound: tiny WAV-chunk decode cadence + false barge-in discard + possible Cartesia context interruption; not Deepgram (STT is input) |
| **Files** | `interview_bot.py`, `manual_client/client.js`, `interview_processor.py`, Cartesia TTS service (Pipecat) |
| **Modules** | Transport serializer, client audio queue, barge-in |
| **Current** | Gaps / mid-sentence dead air |
| **Expected** | Continuous speech |
| **Why** | Streaming design + protective barge-in overfired |
| **Solution** | Transport/jitter/barge thresholds; single TTS frame |
| **Complexity** | Medium–High |
| **Risk** | Medium |
| **Architecture?** | Mostly implementation |

### 4. Duplicate Questions

| Field | Detail |
|-------|--------|
| **Root cause** | PROBE path skips `_ensure_unique_question`; intentional guard repeats amplify perception |
| **Files** | `dialogue_manager.py`, `question_dedup.py`, `decision_engine.py`, `llm_adapter.py`, guard redirect helpers |
| **Modules** | DialogueManager, DecisionEngine, QuestionDedup |
| **Current** | Similar questions can reappear |
| **Expected** | Unique phrasing except explicit repeats |
| **Why** | Dedup wired for ADVANCE, not PROBE |
| **Solution** | Always run uniqueness; better PROBE prompting |
| **Complexity** | Low–Medium |
| **Risk** | Low |
| **Architecture?** | No |

### 5. Transcript Repetition

| Field | Detail |
|-------|--------|
| **Root cause** | Progressive interim + fragmented finals merged by append; VAD flips increase fragments |
| **Files** | `interview_processor.py`, `transcript_utils.py`, `transcript_quality.py`, VAD params in `interview_bot.py` |
| **Modules** | InterviewProcessor merge, STT cleanup |
| **Current** | Duplicated phrases in logs and often in cleaned text |
| **Expected** | Single clean utterance |
| **Why** | Streaming STT semantics + merge heuristic |
| **Solution** | Extension-aware merge; quieter interim logs |
| **Complexity** | Medium |
| **Risk** | Medium |
| **Architecture?** | No |

### 6. Overall Voice Pipeline

| Field | Detail |
|-------|--------|
| **Root cause** | Correct architecture with timing races, serial LLM, missing silence policy, client/server barge mismatch |
| **Files** | Full Pipecat path listed above |
| **Modules** | End-to-end |
| **Current** | Works for demos; fragile UX under silence / barge / long eval |
| **Expected** | Stable turn-taking with explicit timeouts and continuous TTS |
| **Why** | Incremental Phase 5–6 patches without turn-taking state machine |
| **Solution** | Silence policy + merge/dedup/TTS fixes as sequenced above |
| **Complexity** | Medium |
| **Risk** | Medium |
| **Architecture?** | Keep architecture; optionally add TurnTakingPolicy later |

---

## Additional Investigation (Document Only)

### Dead / outdated / duplicated

| Item | Notes |
|------|-------|
| `dialogue/interview_flow_controller.py` | Deprecated; CoverageEngine supersedes |
| `backend/voice/vad_simulator.py`, interruption/streaming helpers | Dev text-WS simulation; not live Pipecat path |
| Root `test_*.py` scripts | Manual Groq explorers; not in regression |
| STAR language in `EVALUATION_SYSTEM_PROMPT` vs technical rules | Prompt inconsistency still present |
| Duplicate closing `TTSSpeakFrame` | `ai_text` may already close + `INTERVIEW_CLOSING_SPOKEN` |
| README “Phase 5 complete” | Docs debt |

### Complexity / maintainability

- Two parallel histories of questions (`question_selector._asked_questions` vs `context.question_history`)  
- Multiple overlapping “repeat question” helpers (`short_repeat_question`, IDK simplify, intent redirects)  
- Guard order vs intent classifications can still fight for edge phrases  

### Performance

- Dominant cost: Groq adaptive evaluate (+ optional rethink) then sometimes another LLM question generate  
- Debounce+grace stack adds multi-second floor even when STT is clean  

### Logging

- INFO-level interim spam obscures finals and makes “transcript repetition” feel worse than cleaned evaluation may be  
- Recommend DEBUG for interim; INFO for cleaned turn text only  

### Scalability

- Single-client WebSocket by design  
- In-memory SessionService — fine for FYP, not multi-tenant  

---

## Architecture Impact

**Keep:** Pipecat pipeline, SessionService, GuardPipeline, CoverageEngine, rubric/evaluation, Cartesia/Deepgram/Groq.

**Do not introduce for Phase 6:** New dialogue engine, emotion models, React rewrite, IRT/CAT, or provider swap unless TTS transport investigation proves Cartesia/WAV headers insufficient.

**Add carefully:** Turn-taking / silence policy beside `VoiceTurnPolicy` (same layer as debounce — natural Phase 6 home).

---

## Priority Ranking

| Priority | Issues |
|----------|--------|
| **Critical** | 2 — Silence / no-answer hang |
| **High** | 4 — Duplicate questions (PROBE hole); 5 — Transcript merge; 3 — TTS gaps; 1 — Robotic phrasing |
| **Medium** | Pipeline races, logging noise, double closing TTS |
| **Low** | Dead-code cleanup, README update, scalability |

---

## Recommended Implementation Order (Roadmap — Not Started)

| Step | Work | Effort | Depends on |
|------|------|--------|------------|
| 1 | Candidate silence nudge + timeout | 1–2 days | — |
| 2 | `_ensure_unique_question` on PROBE + tests | 0.5–1 day | — |
| 3 | Extension-aware transcript merge + quieter logs | 1–2 days | — |
| 4 | Barge-in thresholds + TTS chunk/WAV experiments | 1–3 days | Live retest |
| 5 | Transition/acknowledgement phrase banks + softer redirects | 1–2 days | After 2 (reduce loops first) |
| 6 | Timing race polish + remove double close | 0.5–1 day | — |
| 7 | Docs/README dead-code notes | 0.5 day | End |

**Total estimated effort:** ~1–1.5 weeks calendar for one developer with live retests.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Silence nudge fires while candidate thinks | Longer first timeout; only nudge after bot finished + VAD quiet |
| Merge drops words | Unit tests with real log strings from live sessions |
| Softer redirects weaken off-topic control | Keep redirect *policy*; only change *wording* |
| WAV/PCM transport change breaks client | Feature-flag; A/B on manual client |
| Naturalize LLM pass drifts from blueprint | Constrain rewrite: same intent, vary prologue only |

---

## Final Recommendations

1. **Do not start Phase 7.** These issues are Phase 6 quality/voice.  
2. **Approve implementation in the order above**, starting with silence timeout — it is the only Critical gap with zero current logic.  
3. Treat “robotic” speech as **template dominance**, not persona failure — keep interviewer rules; vary delivery.  
4. Close the **PROBE dedup hole** before investing heavily in conversational polish — otherwise natural phrases will still re-ask similar probes.  
5. Separate **log noise** from **evaluation text noise** when judging transcript quality.  
6. Confirm TTS provider language in docs: **Cartesia**, not ElevenLabs/OpenAI.  
7. **Wait for explicit approval** before any code change.

---

## Evidence Snapshot (Code Anchors)

- No silence timer: processor only schedules turns from transcripts; `idle_timeout_secs=None` in `interview_bot.py`  
- PROBE undeduped: `dialogue_manager.py` else-branch assigns `decision.get("next_question")`  
- Robotic bank: `llm_adapter._naturalize_static_question` fixed `Let's …` strings  
- WAV streaming: `add_wav_header=True` + client `decodeAudioData` per Blob  
- Transcript merge: `InterviewProcessor._merge_transcript_part` append path  

---

*End of Phase 6 Investigation Report — analysis only.*

---

## Deep-Dive Addendum (2026-07-08) — Answers to Follow-up Questions

Analysis only. Still **no implementation**.

### A1. Silence handling — why your silent test produced zero prompts

**Is there a silence timer?** **No.** Confirmed by code inspection of `InterviewProcessor.process_frame`:

- On `BotStoppedSpeakingFrame`: only clears `bot_is_speaking` and sets a short echo cooldown (~0.8s). **No timer started.**
- The only “silence” timer is `_interim_silence_seconds = 1.4`, and it runs **only after interim STT text already exists**. True silence → no interim → that path never runs.
- Deepgram endpointing (~500ms), VAD `audio_idle_timeout=2.0`, debounce (3s), and grace (2.5s) all require speech/transcript first.
- `PipelineTask(idle_timeout_secs=None)` disables pipeline *shutdown*, not “nudge the candidate.”

**Why nothing at ~8 seconds?** That delay was **recommended industry behavior**, not existing product behavior. Your test result is exactly what the code predicts.

| Component | Exists today? | Triggers on total silence? |
|-----------|---------------|----------------------------|
| Candidate no-answer timer after bot finishes | **No** | N/A |
| Interim finalize after 1.4s | Yes | **No** (needs buffered text) |
| Empty final → “I didn't catch that” | Yes | Only if Deepgram emits empty *final* |
| DialogueManager silence policy | **No** | Never called without transcript |

**Where should it live (cleanest, no architecture rewrite)?**

Preferred: **`InterviewProcessor` + `VoiceTurnPolicy`** (same layer as debounce/grace).

```text
BotStoppedSpeakingFrame
  → start asyncio silence task (cancel on speech/interim/final)
  → after nudge_secs: TTSSpeakFrame soft prompt  OR  adapter.handle_silence("nudge")
  → after timeout_secs: adapter.handle_silence("rephrase"|"skip")
```

Alternate (heavier): synthetic event into `DialogueManager` / Meta guard — better if nudges must update report traces; still no SessionService redesign.

**Do not put it in:** Deepgram endpointing alone, VAD alone, or DialogueManager-only (DM never wakes without a turn).

**Complexity:** Medium · **Risk:** Medium (false nudges if quiet speech missed) · **Trade-off:** Wait too long → hang remains; too short → interrupts thinking.

---

### A2. Global duplicate detection before every question

**Is “check before every ask” correct?** **Yes.** This is the right architectural rule for this system.

**Ideal choke point:** one function every outbound interviewer utterance must pass through before `context.add_turn` / TTS — e.g. extend / always call `_ensure_unique_question(...)`.

| Source path today | Dedup? |
|-------------------|--------|
| ADVANCE / `type=ask` via LLMAdapter + `_ensure_unique_question` | Yes |
| PROBE `decision["next_question"]` (evaluator) | **No** ← bug |
| Guard redirects / IDK rephrase | N/A — intentional *same* question |
| Closing | N/A |

**Would global dedup cause problems?**

| Concern | Mitigation |
|---------|------------|
| Blocking intentional repeats (“Can you repeat?”) | Exempt `REPEAT_REQUEST` / explicit repeat intents; or whitelist `decision_type in {REPEAT, CLARIFY_REPEAT}` |
| PROBE too similar to primary after rewrite | On hit: re-prompt LLM “different angle” once, then template fallback (already partially in `_ensure_unique_question`) |
| False positives at 0.82 | Tune threshold; fingerprint domain+intent; ignore shared “how would you…” stems |
| Performance | Negligible (`SequenceMatcher` on ≤20 strings) |

**Placement:** Inside `DialogueManager` immediately before recording/returning the spoken question — **not** only inside `LLMAdapter`, so evaluator PROBEs cannot bypass it. `question_selector` / bank paths already try locally; DM gate is the universal final filter.

**Complexity:** Low–Medium · **Risk:** Low if repeat intents are exempted · **Architecture:** Implementation only (funnel all paths through existing helper).

---

### A3. Garbled transcript aggregation (`I will use… I will use…`)

**Why it works that way:** The pipeline mixes two STT semantics:

1. **Deepgram interims** — progressive hypothesis (each message *replaces* the prior reading of the same utterance).  
2. **Our merger** — `_merge_transcript_part` treats many frames as **appendable parts**, especially when VAD emits several short *finals*.

If neither string is a substring of the other, code **appends**. Progressive near-duplicates (`"I will use"` + `"I will use Python"` that didn’t substring-match due to punctuation/timing) become `"I will use I will use Python"`. Logging every interim at INFO makes this look even worse.

**Deepgram vs us:** Deepgram streaming is normal. **Garbled concat is primarily our aggregation.** Over-sensitive VAD (`SPEAKING↔STOPPING`) multiplies finals and feeds the bad merge.

**Industry standard:**

- Treat **interim** as replaceable `current_hypothesis`.  
- On **final**, commit hypothesis (or replace if final extends/overlaps).  
- Dedupe adjacent repeated n-grams only as a safety net (we already have cleanup; it cannot always undo bad merges).  
- Do **not** concatenate every interim to a growing list as if they were independent turns.

**Latency-safe fix direction:**

- Prefer **replace-when-extends** (prefix / high overlap) over append.  
- Keep one `latest_hypothesis` string; append only on clear *new utterance* after silence.  
- Leave debounce as-is initially (correctness first); optional: finalize sooner when final arrives and merge is replace-only.

**Complexity:** Medium · **Risk:** Medium (over-aggressive replace can drop late words) · **Architecture:** Processor-local.

---

### A4. Audio pauses & false barge-in (headphones now, speakers worse later)

**Two barge-in paths today:**

1. **Client** (`client.js`): RMS `> 0.035` for **3** consecutive ScriptProcessor frames (~few hundred ms), after 400ms bot-start grace → stop playback + send `{type: interrupt}` → server `request_client_interrupt`.  
2. **Server** (`InterviewProcessor`): Silero `VADUserStartedSpeakingFrame` while `bot_is_speaking` → `broadcast_interruption()`.

Headphones reduce AEC issues but **room noise / mouse / breathing** can still trip **RMS 0.035** (quite low). Laptop speakers will be worse: **bot speech leaks into the mic** and looks like barge-in → classic mid-sentence cut.

**How production assistants handle this:**

| Technique | Purpose | Fits our stack? |
|-----------|---------|-----------------|
| Higher energy + longer consecutive frames | Fewer false triggers | **Yes — config first** |
| Ignore barge until bot has spoken N ms / N words | Avoid early cut | Partially have 400ms — likely too short |
| Acoustic Echo Cancellation (AEC) / headset preference | Cancel speaker→mic | Browser limited; document headset |
| Server barge only on **ASR words**, not energy | Noise ≠ speech | **Strong, still modular** |
| Soft mute / duck instead of hard stop | Less jarring | Optional later |
| Full voice activity ML sidecar | Overkill for FYP | Avoid unless config+ASR gate fail |

**Config-only vs more processing:**

1. **Phase 1 (config / params only):** Raise `barge_rms` (e.g. 0.08–0.12), raise `barge_frames` (5–8), lengthen `ignore_after_bot_start_ms` (800–1500), optionally require server VAD confidence. Retest headphones then speakers.  
2. **Phase 2 (small module, recommended if speakers matter):** `BargeInPolicy` shared by client+server: interrupt only if **(energy sustained) AND (interim STT non-empty OR VAD speech duration > X ms)**. No new cloud service.  
3. **Avoid for now:** Separate noise-suppression microservice or heavy ML AEC — complexity >> benefit for FYP.

**Complexity:** Low (config) → Medium (ASR-gated barge) · **Risk:** Higher thresholds reduce *true* early barge-in (acceptable for interview) · **Architecture:** Optional thin `BargeInPolicy`; no pipeline rewrite.

---

### A5. Robotic conversation despite using an LLM

**Why still robotic if we have Groq?** Because for most domain advances the **LLM never authors the spoken question**.

Primary path for technical domains:

```text
domain_questions[domain]  →  _naturalize_static_question()  →  fixed “Let's talk/move…” strings
```

LLM is used heavily for **evaluation** and sometimes for **PROBE** / bank-miss fallback. **Spoken coverage questions are templates.** Soft “Voice-Mode Spoken Rules” in `prompts.py` do not override those hard-coded strings.

**Hard-coded / limiting surfaces:**

1. `_naturalize_static_question` rewrite table (same rhetoric every interview).  
2. Guard redirect strings (`Sure, I'll repeat…`, `Let's stay focused…`, `Please answer this directly…`).  
3. Prompt examples that train the model to say `Got it.` / `Understood.` then ask.  
4. Strict interviewer persona (no coaching) with **no alternate variety bank** for warm professional transitions.

**How to stay structured but human (recommendation, not implement yet):**

| Layer | Keep | Vary with LLM / banks |
|-------|------|------------------------|
| Coverage intent / topic | Fixed blueprint | — |
| Exact wording of primary Q | Optional: template seed | Soft “speakable” rewrite: same intent, different prologue |
| Acknowledgements | — | Small rotating bank or 1-line LLM prefix from last answer |
| Guard redirects | Same *policy* | Shorter, varied phrasing via `short_repeat_question` + phrase bank |
| PROBE | Domain + uniqueness | Already LLM — improve prompt to forbid template openers |

Preferred design: **intent fixed, delivery variable** — one optional `speakable_phrasing()` after uniqueness check, constrained (“do not change technical ask; max 2 sentences; no coaching”).

**Complexity:** Medium · **Risk:** Medium (phrasing drift vs fairness) — mitigate with constraints + tests · **Architecture:** Prompt/template layer only.

---

### Revised priority after this deep dive

1. **Silence timer** — Critical; your test proves zero implementation.  
2. **Global `_ensure_unique_question` gate** — High; correct architecture.  
3. **Replace-style transcript hypothesis** — High; matches your “I will use…” symptom.  
4. **Barge config → optional ASR gate** — High for speaker environments; start config-only.  
5. **Speakable delivery over fixed bank** — High for human-feel; after uniqueness so we don’t polish duplicates.

**Still awaiting explicit approval before any code changes.**
