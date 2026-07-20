# FYP Learning Phases — Tracker

Use this file to track your defense preparation. Study one phase at a time. Mark status as you go.

**Project:** AI Voice Interviewer (`AI-interviewer-fyp-v2`)  
**Authoritative branch:** `uthman`  
**Master technical report:** `docs/FYP_FINAL_REPORT_V03.md`  
**Goal:** Deep enough understanding to explain, modify, troubleshoot, and defend every major part of the system.

---

## How to use

1. Open the prep doc for the current phase.
2. Read it fully once (no code diving required yet).
3. Skim the listed source files to connect names to reality.
4. Answer the self-check questions at the end of that prep doc **without looking**.
5. Mark this tracker, then move to the next phase.

| Status | Meaning |
|--------|---------|
| `todo` | Not started |
| `reading` | Prep doc open / in progress |
| `self-checked` | Answered self-check without notes |
| `done` | Can explain the phase to someone else |

---

## Phase list

| # | Phase | Prep doc | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Architecture & mental model | [`FYP_PREP_PHASE_1_ARCHITECTURE.md`](FYP_PREP_PHASE_1_ARCHITECTURE.md) | `todo` | Three faces, one brain |
| 2 | End-to-end interview lifecycle | _TBD_ | `todo` | Lobby → turns → close → report |
| 3 | Session state, bootstrap, CoverageEngine | _TBD_ | `todo` | Structured interview policy |
| 4 | Dialogue turn pipeline | _TBD_ | `todo` | Guards → eval → decide → generate |
| 5 | Voice pipeline | _TBD_ | `todo` | VAD, STT, TTS, barge-in, silence, tails |
| 6 | Evaluation & scoring | _TBD_ | `todo` | Rubric, rethink, STT fairness |
| 7 | Reporting (Report v2) | _TBD_ | `todo` | Tiers, honesty, HTML/JSON |
| 8 | Frontend & wire protocols | _TBD_ | `todo` | manual_client, conversation_event |
| 9 | Design decisions & evolution | _TBD_ | `todo` | Trade-offs vs proposal |
| 10 | Defense prep | _TBD_ | `todo` | Board Q&A, demo script, limits |

---

## Phase 1 summary (quick reminder)

**One sentence:** Multiple entry points (voice bot, REST API, browser client) all feed the same `SessionService` → `DialogueManager` brain; voice is the product path, REST is for testing.

---

## Related reference docs (do not replace prep docs)

| Doc | When to open |
|-----|----------------|
| `FYP_FINAL_REPORT_V03.md` | Full thesis-style narrative |
| `ARCHITECTURE.md` | Short runtime diagram |
| `DEVELOPER_ONBOARDING.md` | Quick layout + how to run |
| `CONFIGURATION.md` | Env vars |
| `dev_file.md` | Older deep walkthrough (verify against current code) |

---

## Progress log

| Date | Phase | What you finished |
|------|-------|-------------------|
| | | |

---

*Prep docs are teaching materials for defense. Prefer live code on `uthman` if a prep doc and an older phase report disagree.*
