# Phase 6C — Reporting & Completion Clarity (Complete)

**Status:** Implemented and tested  
**Scope:** Communication vs technical score profiles, `not_assessed` domains, clearer final reports

---

## Executive Summary

Phase 6C separates how scores are **reported** without adding new evaluation engines. Final reports now include communication vs technical composites, blueprint-level domain assessment (`covered_*` vs `not_assessed`), and interview completion stats. Guard-blocked turns are traced with `guard_passed: false`.

---

## Problems Addressed

| Problem | Fix |
|---------|-----|
| Single blended score hides communication vs technical gaps | `score_profile_summary` via `aggregate_profile_scores()` |
| Uncovered skills shown as "not covered" when skipped by guards | `not_assessed` status in skill coverage + domain assessment map |
| Reports lack completion context | `interview_completion` section (coverage %, assessed/skipped counts) |
| Guard turns invisible in adaptive trace | `guard_passed: false` + `transcript_quality` on non-evaluated traces |
| Recruiter report used ad-hoc dimension mapping | `recruiter_report.py` uses profile composites |

---

## Files Added / Modified

### Added
| File | Purpose |
|------|---------|
| `backend/tests/test_phase6c_reporting.py` | 4 unit tests |

### Modified
| File | Why |
|------|-----|
| `backend/dialogue/context.py` | `assessed_domains`, `skipped_domains`, mark helpers |
| `backend/dialogue/analytics.py` | `build_domain_assessment_map()`, `build_interview_completion_summary()`, report sections |
| `backend/dialogue/recruiter_report.py` | `score_profile_summary`; communication/technical composites |
| `backend/dialogue/dialogue_manager.py` | `mark_domain_assessed` on scored turns; guard traces; profile fields in trace |
| `backend/evaluation/rubric.py` | `COMMUNICATION_DIMENSIONS`, `TECHNICAL_DIMENSIONS`, `aggregate_profile_scores()` |
| `scripts/run_regression.sh` | Phase 6C suite |

---

## New Report Sections

### `score_profile_summary`
```json
{
  "communication": { "clarity": 3.0, "structure": 3.5, "confidence": 3.0, "composite": 3.17 },
  "technical": { "ownership": 4.0, "leadership": 3.0, "result_orientation": 3.5, "composite": 3.5 },
  "turns_included": 5
}
```

### `domain_assessment_map`
Per blueprint domain: `status` (`covered_strong` / `covered_weak` / `not_assessed`), `coverage_turns`, `reason`.

### `interview_completion`
```json
{
  "completed": true,
  "blueprint_domains_total": 10,
  "domains_assessed": 4,
  "domains_not_assessed": 6,
  "coverage_percent": 40.0,
  "not_assessed_domains": ["machine_learning", "..."],
  "completion_note": "..."
}
```

---

## Adaptive Trace Fields (evaluated turns)

- `guard_passed: true`
- `transcript_quality` — noise signals from Phase 6B
- `transcript_quality_adjusted` — whether noisy re-weighting applied
- `score_profiles` — per-turn communication/technical breakdown

## Adaptive Trace Fields (guard-blocked turns)

- `guard_passed: false`
- `transcript_quality` — still recorded for audit
- `metadata` — guard flow action (e.g. `skip_domain`)

---

## Tests

```bash
cd AI-interviewer-fyp-v2
source .venv/bin/activate
export PYTHONPATH=backend
python backend/tests/test_phase6c_reporting.py
```

**Result:** 4/4 Phase 6C tests pass.

---

## Manual Verification

After a voice interview, open the saved report JSON and confirm:

1. `score_profile_summary` present with `communication.composite` and `technical.composite`
2. `domain_assessment_map` lists all blueprint domains
3. Skipped/meta/IDK domains show `not_assessed` (not falsely `covered`)
4. `interview_completion.coverage_percent` reflects assessed vs total blueprint domains
5. Guard turns in `adaptive_questioning_trace` have `guard_passed: false`
