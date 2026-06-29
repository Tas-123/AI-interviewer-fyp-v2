# AI Voice Interviewer

Real-time AI Voice Interviewer project for conducting AI Engineer interview practice using voice input, STT, TTS, dialogue management, adaptive questioning, and interview report generation.

## Project Status

This is version `v0.1 untuned`.

The project is currently under active development. Some live interview behavior may still need tuning, especially around:

* STT transcript cleanup
* Echo detection
* Incomplete answer handling
* Final report formatting
* Real-time voice flow stability

## Main Features

* Real-time voice interview flow
* Browser-based manual client
* WebSocket audio streaming
* Deepgram STT integration
* Cartesia TTS integration
* DialogueManager-based interview logic
* Adaptive technical questioning
* Candidate answer evaluation
* Final interview report generation
* Debug log support for live testing

## Tech Stack

* Python
* FastAPI / WebSocket flow
* Pipecat integration
* Deepgram STT
* Cartesia TTS
* Groq / LLM-based evaluation
* Browser manual client using HTML and JavaScript

## Architecture (Phase 1)

| Runtime | Command | Port | Role |
|---------|---------|------|------|
| **Pipecat voice** (primary) | `python backend/pipecat_integration/interview_bot.py` | WS `8765`, report HTTP `8766` | Product demo |
| **FastAPI REST** | `uvicorn main:app --reload` | `8000` | API/testing without mic |
| **Dev text WebSocket** | Set `ENABLE_DEV_TEXT_VOICE_WS=true` in `.env` | `8000` | Text simulation only |

All runtimes share one in-process `SessionService` when run in the same process. REST `/start` and `/chat` use the same session store as the Pipecat voice adapter.

## Folder Structure

```text
backend/
  core/
    config.py
    session_service.py
    interviewer_policy.py
  dialogue/
    guards/
    transcript_utils.py
    followup_policy.py
    output_sanitizer.py
    analytics.py
    context.py
    database.py
    decision_engine.py
    dialogue_manager.py
    evaluator.py
    llm_adapter.py
    prompts.py
    recruiter_report.py

  integration/
    dialogue_adapter.py

  pipecat_integration/
    interview_bot.py
    interview_processor.py
    manual_client/
      index.html
      client.js

  voice/
    conversation_orchestrator.py
    interruption_manager.py
    streaming_response_handler.py
    voice_session_manager.py

main.py
requirements.txt
requirements-pipecat.txt
.env.example
```

## Setup Instructions

### 1. Clone the repository

```powershell
git clone https://github.com/Tas-123/ai-voice-interviewer.git
cd ai-voice-interviewer
```

### 2. Create virtual environment

```powershell
python -m venv venv
```

Activate it:

```powershell
venv\Scripts\activate
```

### 3. Install dependencies

First try:

```powershell
pip install -r requirements.txt
```

If working on Pipecat voice integration, also install:

```powershell
pip install -r requirements-pipecat.txt
```

## Environment Variables

Create a `.env` file in the root folder.

You can copy `.env.example`:

```powershell
copy .env.example .env
```

Then add your own API keys inside `.env`.

Example:

```env
GROQ_API_KEY=your_groq_api_key_here
DEEPGRAM_API_KEY=your_deepgram_api_key_here
CARTESIA_API_KEY=your_cartesia_api_key_here
```

Important:

Do not commit `.env` to GitHub.
Only `.env.example` should be shared.

## Running the REST API (optional — testing without microphone)

```powershell
uvicorn main:app --reload
```

Then `POST /start` with resume data, `POST /chat` with answers, `GET /report/{session_id}`.

## Running the Voice Interview Server (primary)

From the project root:

```powershell
venv\Scripts\activate
python backend\pipecat_integration\interview_bot.py
```

Expected server:

```text
ws://localhost:8765
```

## Running the Manual Browser Client

Open a second terminal:

```powershell
cd backend\pipecat_integration\manual_client
python -m http.server 3000
```

Then open browser:

```text
http://localhost:3000
```

Allow microphone permission when the browser asks.

## Viewing Latest Report

If report server is running, open:

```text
http://localhost:8766/latest-report
```

## Debugging Live Interview Flow

See [docs/DIALOGUE_PIPELINE.md](docs/DIALOGUE_PIPELINE.md) for guard order and turn flow.

See [docs/INTERVIEW_FLOW.md](docs/INTERVIEW_FLOW.md) for optional resume, blueprint coverage, and session bootstrap (Phase 3).

A clean debug log may be available at:

```text
logs/live_interview_debug.log
```

Useful command:

```powershell
Get-Content .\logs\live_interview_debug.log -Tail 250
```

This log should show:

```text
BOT_LAST_QUESTION
CANDIDATE_RAW_TRANSCRIPT
CANDIDATE_CLEAN_TRANSCRIPT
DECISION
BOT_NEXT_QUESTION
```

## Common Commands

Run main Pipecat interview bot:

```powershell
python backend\pipecat_integration\interview_bot.py
```

Run manual client:

```powershell
cd backend\pipecat_integration\manual_client
python -m http.server 3000
```

Compile important files:

```powershell
python -m py_compile backend\dialogue\dialogue_manager.py
python -m py_compile backend\pipecat_integration\interview_processor.py
```

Run tests if needed:

```powershell
python backend\test_dialogue_adapter.py
python backend\test_pipecat_integration.py
```

## Known Issues

This version is not fully tuned yet.

Known issues may include:

1. Echo guard can sometimes misclassify real candidate answers.
2. STT may produce repeated transcript chunks.
3. Incomplete candidate answers may need better handling.
4. Final report formatting may need more technical-rubric tuning.
5. Browser client and real-time voice flow may require testing on each machine.
6. Database may show this warning if PostgreSQL dependency is not installed:

```text
[Database] Connection failed: No module named 'psycopg2'
```

This warning is not always blocking for local testing.

## Notes for Team Members

Before running the project, make sure:

* Python is installed.
* Virtual environment is activated.
* Dependencies are installed.
* `.env` file is created.
* Required API keys are added.
* Microphone permission is allowed in browser.
* Server is running before opening the browser client.

## Git Workflow

Before making changes:

```powershell
git pull
```

After making changes:

```powershell
git status
git add .
git commit -m "Describe your change"
git push
```

## Repository

```text
https://github.com/Tas-123/ai-voice-interviewer
```
