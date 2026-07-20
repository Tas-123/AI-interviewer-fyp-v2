# Recruiter Dashboard

Separate management UI for creating interview invite links and viewing Report v2 files.
Does **not** run the voice interview engine.

## Ports

| Service | Port | Command |
|---------|------|---------|
| **Recruiter Dashboard** | **8001** | See below |
| Candidate UI | 3000 | `python -m http.server 3000` in `backend/pipecat_integration/manual_client/` |
| Voice bot (WS) | 8765 | `python backend/pipecat_integration/interview_bot.py` |
| Report HTTP (voice) | 8766 | started with the voice bot |
| FastAPI text API (optional) | 8000 | `uvicorn main:app --reload` |

## Run

From this directory:

```bash
cd recruiter_dashboard
pip install -r requirements.txt   # if needed (fastapi, uvicorn, python-dotenv)
uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Open [http://localhost:8001](http://localhost:8001).

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `CANDIDATE_ORIGIN` | `http://localhost:3000` | Base URL baked into invite links |

Set in project root `.env` (loaded automatically) or `recruiter_dashboard/.env`.

## Demo flow

1. Start voice bot (`:8765` / `:8766`).
2. Start Candidate UI (`:3000`).
3. Start Recruiter Dashboard (`:8001`).
4. In **AI Interview**, select role → **Generate interview link** → copy.
5. Open the link (includes `?invite=TOKEN`). Candidate resolves role from this API, then runs the existing lobby → voice interview.
6. After the interview ends, open **Candidate Reports** and refresh. Reports are read from project `reports/*.json` (Report v2).

## Candidate Reports UI

Each row has a compact action group:

| Button | Behavior |
|--------|----------|
| **View** (primary) | Centered **summary modal** — scores, hire signal, narratives; close with Close / backdrop / Esc |
| **Full Report** | HTML assessment in a new browser tab |
| **Download** | Save the HTML file (`/html?download=1`) |

Modal footer repeats Full Report / Download for convenience. Summary is never injected under the table.

Key UI files:

- `static/js/reportsView.js` — table + modal open/close
- `static/css/main.css` — `.action-group`, `.modal*` styles
- `static/index.html` — `#report-modal` markup

## Limitations (FYP)

- **One live voice session** at a time on the Pipecat bot.
- Invite store is a local JSON file (`data/interviews.json`) — fine for demos, not multi-user production.
- No recruiter login in v1.
- Interview engine (`DialogueManager` / Pipecat) is not imported or modified by this module.

## API (summary)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/roles` | Role dropdown |
| `GET` | `/api/interviews` | List invites |
| `POST` | `/api/interviews` | Create invite `{ target_role, label? }` |
| `GET` | `/api/interviews/{token}` | Resolve invite (Candidate) |
| `POST` | `/api/interviews/{token}/bind` | Bind `{ session_id }` |
| `GET` | `/api/reports` | List Report v2 cards from disk |
| `GET` | `/api/reports/{session_id}` | Full Report v2 JSON |
| `GET` | `/api/reports/{session_id}/html` | Sibling HTML (inline in browser) |
| `GET` | `/api/reports/{session_id}/html?download=1` | Same HTML as a file download |
