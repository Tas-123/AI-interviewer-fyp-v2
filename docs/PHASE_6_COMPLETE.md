# Phase 6 Completion Report — Interview Quality & Voice Experience

**Status:** Fully complete (implementation + automated regression)  
**Date:** 2026-07-08  
**Branch:** `uthman`  
**Scope:** Phase 6 improvements only (no Phase 7)  
**TTS:** Cartesia · **LLM:** Groq · **STT:** Deepgram  

---

## 1. Executive Summary

Phase 6 closes five approved interview-quality gaps without redesigning the Pipecat → DialogueManager pipeline:

1. **Silence handling** — nudge (~8s) then rephrase (~15s) after the bot finishes speaking  
2. **Global duplicate question detection** — PROBE / legacy paths now go through `_ensure_unique_question`  
3. **Transcript aggregation** — replace-when-extends STT merge instead of blind append  
4. **False barge-in reduction** — higher client RMS thresholds + 1s server VAD grace  
5. **Natural conversation** — rotating openers, softer redirects, varied acknowledgement prompts  

All five items were implemented and unit-tested sequentially. Full `scripts/run_regression.sh` passes. Architecture impact is local (policy/config + small helpers). Phase 6 is **complete and ready for live voice validation**; mark **production-ready for text/pipeline correctness**, with a short live checklist remaining for absolute production confidence on silence/barge timing.

---

## 2. Features Implemented

### 2.1 Silence Handling
- On `BotStoppedSpeakingFrame`, schedule a silence watch (after a short settle delay for chained TTS).
- Soft nudge TTS, then rephrase TTS if the candidate stays silent.
- Cancel on VAD start, interim/final STT, turn submit, or client interrupt.
- Stage lock (`watching` / `nudged` / `done`) prevents nudge TTS from restarting an infinite watch loop.
- Configurable via `CANDIDATE_SILENCE_NUDGE_SECONDS` / `CANDIDATE_SILENCE_REPHRASE_SECONDS` (0 disables).

### 2.2 Global Duplicate Question Detection
- Evaluator **PROBE** `next_question` and legacy follow-ups now call `_ensure_unique_question`.
- Default similarity threshold lowered slightly (`0.82` → `0.80`).
- Intentional guard repeats / closing statements remain exempt by path.

### 2.3 Transcript Aggregation Fix
- New `merge_stt_hypothesis()` prefers replace-when-extends / high overlap over append.
- Wired into `InterviewProcessor._merge_transcript_part`.
- Interim STT buffered logs moved to DEBUG (INFO only for finals).

### 2.4 False Barge-In Improvements
- Client defaults: RMS `0.09`, min frames `6`, ignore-after-bot-start `1000` ms.
- Server: ignore Silero barge-in for `BARGE_IN_MIN_BOT_SPEAK_SECONDS` (default `1.0`) after bot TTS starts.
- Query-string overrides preserved for live tuning.

### 2.5 Natural Conversation Improvements
- Domain bank delivery: fixed cores + rotating short openers (`""`, `Alright —`, `Next up:`, …).
- Softened intent/domain redirects (“Happy to repeat…”, “Let's come back to this…”).
- Prompt acknowledgement examples diversified; style rules discourage “Let's talk/move…” every turn.

---

## 3. Files Modified

| Area | Files |
|------|--------|
| Silence | `backend/pipecat_integration/interview_processor.py`, `backend/voice/voice_turn_policy.py`, `backend/core/config.py`, `.env.example` |
| Dedup | `backend/dialogue/dialogue_manager.py`, `backend/dialogue/question_dedup.py` |
| Transcripts | `backend/dialogue/transcript_utils.py`, `interview_processor.py` |
| Barge-in | `manual_client/config.js`, `manual_client/client.js`, `voice_turn_policy.py`, `config.py`, `interview_processor.py` |
| Natural | `llm_adapter.py`, `guards/domain_guard.py`, `guards/intent_guard.py`, `guards/echo_guard.py`, `prompts.py` |
| Tests | `test_phase6_silence_handling.py`, `test_phase6_duplicate_questions.py`, `test_phase6_transcript_aggregation.py`, `test_phase6_barge_in.py`, `test_phase6_natural_conversation.py`, plus updates to 6A / adapter / flow / policy / pipecat integration tests |
| Regression | `scripts/run_regression.sh` |

**New documentation:** this report (`docs/PHASE_6_COMPLETE.md`).

---

## 4. Architecture Impact

| Question | Answer |
|----------|--------|
| Pipeline redesigned? | **No** |
| New services? | **No** |
| Where silence lives | `InterviewProcessor` + `VoiceTurnPolicy` (correct layer; DM remains turn-driven) |
| Dedup choke point | `DialogueManager._ensure_unique_question` |
| Merge logic | Shared helper in `transcript_utils`; processor calls it |
| Barge policy | Config defaults + one processor grace field |

---

## 5. Testing Performed

### Per-feature (immediate)

| Feature | Automated | Result |
|---------|-----------|--------|
| Silence | `test_phase6_silence_handling.py` (nudge+rephrase, cancel on speech, no restart on nudge BotStopped) | PASS |
| Dedup | `test_phase6_duplicate_questions.py` | PASS |
| Aggregation | `test_phase6_transcript_aggregation.py` + processor smoke | PASS |
| Barge-in | `test_phase6_barge_in.py` (early VAD ignored, late interrupts, config defaults) | PASS |
| Natural | `test_phase6_natural_conversation.py` + guard/flow suites | PASS |

### Full regression
`scripts/run_regression.sh` — **all checks passed** (6A–6C, new Phase 6 suite, transcript utils, voice policy, Phase 3/4, Pipecat dry-run, dialogue adapter).

### Manual / live
- Not executed in this session (no live mic/Cartesia run). Recommended checklist below.
- Guard redirect wording verified via existing echo/redirect scripts (observed softer strings when LLM offline).

---

## 6. Edge Cases Verified

| Edge case | Outcome |
|-----------|---------|
| Silence nudge TTS finishing (`BotStopped`) while watch in `nudged` | Does not spawn a second watch |
| Settle delay while chained TTS still speaking | Watch aborts; later BotStopped can reschedule |
| Progressive interim `"My name is"` → longer form | Replaces, does not duplicate |
| True new clause after prior sentence | Still appends |
| PROBE wording ≈ prior primary | Replaced with uniqueness fallback |
| VAD within 1s of bot start | No server interrupt |
| VAD after grace | Interrupt broadcasts |
| Domain redirect nested history | Canonical strip still works with new soft prefixes |

---

## 7. Regression Results

Verified by automated suite that:

- Voice processor turn handling / empty transcript / error fallback / completion still pass  
- Dialogue adapter start → multi-turn → report path still passes (assertions updated for new phrasing)  
- Coverage engine / evaluation / Phase 6B–6C reporting still pass  
- Silence, dedup, merge, barge, natural unit suites pass  

**Live checklist (recommended before declaring production absolute):**

- [ ] Voice input + Deepgram finals correct  
- [ ] Cartesia speaks silence nudge then rephrase (~8s / ~15s) when mic silent  
- [ ] Speaking within window cancels silence prompts  
- [ ] No duplicate domain/probe questions in a full interview  
- [ ] Transcript in UI/logs is one coherent turn (no “I will use I will use…”)  
- [ ] Headphones: negligible false barge mid-question  
- [ ] Evaluation + PDF/JSON report still generated  
- [ ] Conversation openers vary; redirects feel shorter  

---

## 8. Remaining Limitations

1. **Silence timings** use wall-clock after BotStopped settle — very long multi-chunk TTS may still start timing slightly early (settle + stage lock mitigate).  
2. **No “skip domain after second silence”** (was optional in investigation); only nudge + rephrase.  
3. **Barge-in is energy / VAD grace**, not full ASR-gated barge (optional Phase 2 in investigation — not required for this delivery).  
4. **Natural openers rotate deterministically by turn index** — intentional (no extra LLM cost); less variety than a full speakable-LLM pass.  
5. **WAV-per-chunk mid-sentence gaps** (Cartesia transport) were investigated but **not** redesigned here (user order prioritized barge config first).  
6. Live A/B on laptop speakers vs headphones not run in this session.

---

## 9. Performance Impact

| Change | Impact |
|--------|--------|
| Silence asyncio task | Negligible; sleeps only |
| Dedup `SequenceMatcher` on ≤~20 questions | Negligible |
| `merge_stt_hypothesis` | Cheaper than prior multi-path merge |
| Higher barge thresholds | Slightly fewer interrupt round-trips (net positive) |
| Naturalize rotation | No extra LLM calls |

No measurable throughput degradation expected.

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| Silence nudge while candidate thinks | Defaults 8s / 15s; env-tunable; cancel on any speech |
| Stricter merge dropping late words | Unit tests for append-on-new-clause; overlap ≥1 token |
| Harder true early barge-in | Acceptable for interviews; query overrides available |
| Soft redirects weaker control | Same policy triggers; only wording changed |
| Old tests expecting “Let's talk about…” | Updated |

---

## 11. Recommendations

1. Run the live checklist once on headphones, then briefly with speakers.  
2. Tune `CANDIDATE_SILENCE_*` and `barge_*` query params from that session if needed.  
3. Do **not** start Phase 7 until live silence + barge feel validated.  
4. Optional follow-ups still in Phase 6 spirit (only if needed): ASR-gated barge, WAV transport experiment, skip-after-double-silence.  

---

## Verdict

| Criterion | Status |
|-----------|--------|
| All five Phase 6 tasks implemented | **Yes** |
| Tested after each task | **Yes** |
| Full regression green | **Yes** |
| Architecture preserved | **Yes** |
| Phase 7 started | **No** |
| **Phase 6 fully complete** | **Yes** |
| **Production-ready** | **Yes for pipeline / dialogue correctness**; complete one live voice pass for production absolute confidence |

---

*End of Phase 6 Completion Report*
