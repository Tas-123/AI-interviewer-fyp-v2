# Recruiter Report Contract (Report v2)

**Status:** Canonical presentation contract for FYP + future Recruiter Dashboard  
**Data source of truth:** Report v2 JSON on disk (`reports/interview_report_*.json`)  
**Recruiter presentation (FYP):** HTML from `reporting.renderers.html_renderer.render_report_html`  
**Candidate UI:** Completion / thank-you message only — not a second score view  

---

## Architecture

```
InterviewContext → generate_final_report → build_report_v2 → JSON (+ HTML)
                                                      ↓
                              Candidate: thank-you + link to HTML
                              Recruiter (later): Dashboard reads same JSON keys
```

- **Do not** scrape HTML as the API.
- **Do not** teach a future dashboard to depend on legacy root keys (`weighted_score_summary`, `adaptive_questioning_trace`, …) for primary UI.
- Legacy keys remain mirrored at the JSON root for backward compatibility / debug only.

---

## Required presentation fields

| Field | Purpose |
|-------|---------|
| `report_meta.candidate_display_name` | Hero name |
| `report_meta.role_title` | Role under review |
| `report_meta.report_type` | `complete` \| `partial` \| `incomplete` \| `aborted` |
| `report_meta.session_id` | Traceability |
| `report_meta.generated_at` | Timestamp |
| `ratings_summary.final_recommendation` | `{ signal, rationale, confidence, disclaimer }` |
| `ratings_summary.overall_performance` | `{ score, label }` |
| `ratings_summary.technical_performance` | `{ score, label }` |
| `ratings_summary.communication_skills` | `{ score, label }` |
| `executive_summary` | Short recruiter narrative |
| `overall_summary` | Supporting paragraph |
| `strengths` | Bullet list |
| `areas_for_improvement` | Bullet list |
| `domain_ratings[]` | Domain / status / rating / note |
| `question_review[]` | Condensed Q&A review |
| `interview_completion` | Coverage, turns, termination, notes |
| `limitations_and_bias` | Caveats (esp. non-complete) |

Hire signal for recruiter UI: **always** `ratings_summary.final_recommendation.signal`  
(Non-`complete` reports force `N/A` by design.)

---

## Filenames

Pattern (already implemented):

`interview_report_{candidate_slug}_{YYYYMMDD_HHMM}_{session_id[:8]}.json`  
Sibling HTML uses the same stem with `.html`.

---

## Local demo endpoints (port 8766)

| Path | Returns |
|------|---------|
| `GET /latest-report` | `{ file, html_file, html_url, report }` |
| `GET /latest-report.html` | Latest recruiter HTML |

---

## Future Recruiter Dashboard

1. `GET /api/recruiter/reports/{session_id}` → Report v2 JSON (same fields above).  
2. Render the same section order as the HTML assessment.  
3. Keep candidate-facing product limited to a completion confirmation.

---

## Explicit non-goals (for this contract)

- Candidate-facing score breakdown  
- Dual detailed UIs (JS + HTML) kept in sync forever  
- Replacing JSON with HTML as the store  
- Auth / multi-tenant portal in the FYP pass  
