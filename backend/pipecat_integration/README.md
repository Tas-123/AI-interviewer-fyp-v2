# Pipecat Voice Layer Integration

This directory contains the integration of **Pipecat** as a voice-only pipeline that connects to the existing `InterviewDialogueAdapter`. 

The core dialogue engine (`DialogueManager`) remains the sole "brain" of the application, managing evaluation, state transitions, and logic, while Pipecat handles transcription (STT), voice synthesis (TTS), and real-time streaming transport.

## Architecture

The data flows through the following pipeline:

```
[WebSocket Client (Audio)]
       │ (Input Stream)
       ▼
[WebsocketServerTransport]
       │ (Audio Frames)
       ▼
[DeepgramSTTService] (Speech-to-Text)
       │ (TranscriptionFrames)
       ▼
[InterviewProcessor] (Custom FrameProcessor)
       │ ──(Calls process_user_text)──► [InterviewDialogueAdapter]
       │ ◄──(Returns AI response)────── [DialogueManager]
       │ (Transforms to TextFrames)
       ▼
[CartesiaTTSService] (Text-to-Speech)
       │ (Audio Frames)
       ▼
[WebsocketServerTransport]
       │ (Output Stream)
       ▼
[WebSocket Client (Audio)]
```

- **No separate LLM** is run within Pipecat. All dialogue orchestration is bridged via the adapter layer.
- The pipeline gracefully terminates and shuts down (using `EndTaskFrame` upstream) when the adapter transitions to the `wrapup` state and returns `is_complete=True`.
- On connection teardown, `adapter.end_interview` is automatically called to persist scores, consistency rating, and trend labels to the database.

## Files

1. **`config.py`**: Configuration helper reading API keys and options from environment variables.
2. **`interview_processor.py`**: Custom `InterviewProcessor` inheriting from `FrameProcessor` that intercepts text transcription frames, queries the adapter, pushes reply text frames, and triggers end tasks.
3. **`interview_bot.py`**: Main application that builds the pipeline and starts the WebSocket server.

## Installation

1. Install Pipecat dependencies:
   ```bash
   pip install -r requirements-pipecat.txt
   ```

2. Standard system dependencies required for `silero` and local audio processing may apply.

## Environment Variables

Make sure to set the following environment variables before running:

```bash
export DEEPGRAM_API_KEY="your-deepgram-api-key"
export CARTESIA_API_KEY="your-cartesia-api-key"
export GEMINI_API_KEY="your-gemini-api-key" # Required for dialogue manager LLM calls
```

Optional settings:
- `CARTESIA_VOICE_ID`: Voice ID to use for TTS (defaults to British male voice `2d1cc513-e4d7-466c-bb9a-cb7127e79391`).
- `PIPECAT_WS_HOST`: Host to bind WebSocket server to (default `localhost`).
- `PIPECAT_WS_PORT`: Port to bind WebSocket server to (default `8765`).

## Running the Bot

Run the bot with the following command:

```bash
python backend/pipecat_integration/interview_bot.py
```

It starts a standalone WebSocket server at `ws://localhost:8765`.

## Verification and Testing

### Dry-Run Tests (No Pipecat Required)
We provide a standalone suite that tests the adapter-to-processor lifecycle, handling of empty transcripts, error recovery, and wrap-up logic without requiring the installation of the Pipecat framework:

```bash
python backend/test_pipecat_integration.py
```
