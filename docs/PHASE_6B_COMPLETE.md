# Phase 6B — Transcript Quality & Fair Evaluation (Complete)

**Status:** Implemented and tested  
**Scope:** STT cleanup, noisy-transcript detection, fairer scoring — builds on Phase 6A flow

---

## Executive Summary

Phase 6B addresses unfair scoring caused by garbled speech-to-text output. Repeated STT fragments, stutter prefixes, and phrase echoes are cleaned before evaluation. When noise is detected, communication dimensions are down-weighted so technical substance is not drowned out by ASR artifacts.

---

## Problems Addressed

| Problem | Fix |
|---------|-----|
| Repeated STT phrases inflate word count | `clean_live_transcript()` + stutter-prefix removal |
| Noisy transcripts penalize clarity/structure unfairly | `assess_transcript_quality()` + `apply_transcript_quality_adjustment()` |
| Evaluator unaware of STT issues | `transcript_quality` passed into evaluator prompt and pipeline |
| Deepgram defaults not tuned for technical terms | Configurable model, endpointing, smart_format, keywords |

---

## Files Added / Modified

### Added
| File | Purpose |
|------|---------|
| `backend/dialogue/transcript_quality.py` | `TranscriptQuality` dataclass; noise scoring |
| `backend/tests/test_phase6b_transcript_quality.py` | 4 unit tests |

### Modified
| File | Why |
|------|-----|
| `backend/dialogue/transcript_utils.py` | `_remove_stutter_prefix()`, `prepare_transcript_for_evaluation()` |
| `backend/evaluation/rubric.py` | `NOISY_TRANSCRIPT_WEIGHTS`, `apply_transcript_quality_adjustment()`, profile helpers |
| `backend/dialogue/evaluation_pipeline.py` | Applies quality adjustment after primary/rethink |
| `backend/dialogue/evaluator.py` | Noisy-STT note in adaptive prompt |
| `backend/dialogue/dialogue_manager.py` | Uses `prepare_transcript_for_evaluation()`; logs quality |
| `backend/core/config.py` | Deepgram STT env settings |
| `backend/pipecat_integration/interview_bot.py` | `DeepgramSTTService.Settings` wiring |
| `.env.example` | Deepgram tuning variables |
| `backend/tests/test_transcript_utils.py` | Stutter-prefix test |
| `scripts/run_regression.sh` | Phase 6B suite |

---

## Evaluation Flow (Phase 6B)

```
handle_turn(transcript)
  → prepare_transcript_for_evaluation()
       → clean_live_transcript()
       → assess_transcript_quality()
  → GuardPipeline (unchanged from 6A)
  → adaptive_evaluate(transcript_quality=...)
  → apply_transcript_quality_adjustment()  [if is_noisy]
```

---

## Configuration

New `.env` variables:

```env
DEEPGRAM_MODEL=nova-2
DEEPGRAM_LANGUAGE=en
DEEPGRAM_ENDPOINTING_MS=500
DEEPGRAM_SMART_FORMAT=true
DEEPGRAM_PUNCTUATE=true
DEEPGRAM_KEYWORDS=FastAPI:1,Qdrant:1,Python:1,TensorFlow:1,scikit-learn:1
```

---

## Tests

```bash
cd AI-interviewer-fyp-v2
source .venv/bin/activate
export PYTHONPATH=backend
python backend/tests/test_phase6b_transcript_quality.py
bash scripts/run_regression.sh   # use .venv/bin/python if system python lacks deps
```

**Result:** 4/4 Phase 6B tests pass; full regression passes with venv.

---

## Manual Voice Retest Checklist

1. Start bot: `python backend/pipecat_integration/interview_bot.py`
2. Open manual client at `http://localhost:8888/...` (or your configured port)
3. Speak with intentional repetition / false starts
4. Confirm report shows `transcript_quality` on adaptive trace entries
5. Confirm noisy turns use `transcript_quality_adjusted: true` when applicable

---

## Next

Phase 6C (reporting separation) is implemented in parallel — see `docs/PHASE_6C_COMPLETE.md`.
