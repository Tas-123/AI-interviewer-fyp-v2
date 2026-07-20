# Recruiter Dashboard

**Status:** Implemented as a separate module (`recruiter_dashboard/`)  
**Does not modify:** DialogueManager, Pipecat processor, CoverageEngine, or Report v2 generation.

## Role in the system

```
Recruiter UI (:8001)  →  invite JSON + read reports/
Candidate UI (:3000)  →  ?invite=TOKEN → resolve role → existing voice bot
Voice bot (:8765)     →  unchanged interview engine → writes reports/
```

Recruiters manage **who interviews for which role** and **read finished Report v2 files**.  
The interview brain stays independent.

## Run ports

| Process | Port | Notes |
|---------|------|-------|
| Recruiter Dashboard | **8001** | `cd recruiter_dashboard && uvicorn app:app --reload --port 8001` |
| Candidate Interface | 3000 | Existing `manual_client` static server |
| Voice bot WS | 8765 | Primary product path |
| Voice report HTTP | 8766 | Still used by Candidate thank-you / latest-report |
| FastAPI (optional) | 8000 | Text testing only |

## Environment

```bash
CANDIDATE_ORIGIN=http://localhost:3000
```

Invite links are `{CANDIDATE_ORIGIN}/?invite={token}`.

Optional Candidate override: `?recruiter=http://localhost:8001` if the Recruiter API is not on the default host.

## Invite lifecycle

1. Recruiter `POST /api/interviews` → token stored in `recruiter_dashboard/data/interviews.json`.
2. Candidate opens link → `GET /api/interviews/{token}` → `target_role` applied to WS `start` payload.
3. On `conversation_event` session started → `POST .../bind` with `session_id`.
4. On voice disconnect, engine writes `reports/interview_report_*.json` as before.
5. Recruiter `GET /api/reports` indexes disk Report v2 (contract fields only).

## Candidate Reports UI

Reports table actions (compact equal-height button group):

| Action | Behavior |
|--------|----------|
| **View** | Opens a **centered summary modal** (backdrop; close via Close, backdrop click, or Esc) |
| **Full Report** | Opens the sibling HTML assessment in a **new tab** (`/api/reports/{session_id}/html`, inline) |
| **Download** | Saves the same HTML locally (`?download=1`, `Content-Disposition: attachment`) |

The modal shows Report v2 screening fields (scores, hire signal, executive/overall summaries, rationale) plus footer links for Full Report / Download. It does **not** render below the table.

## Single-session limitation

The Pipecat voice bot still supports **one concurrent live interview**. Share one invite at a time while the bot is running.

## Compatibility

- Report source of truth remains Report v2 JSON on disk (see `RECRUITER_REPORT_CONTRACT.md`).
- Dashboard does not scrape HTML for API data; HTML is opened as a sibling file when present.
- Hire signal: `ratings_summary.final_recommendation.signal`.

## Module layout

See `recruiter_dashboard/README.md`.
