# Pipecat WebSocket Bot — Manual Browser Client

This directory contains a minimal, beautiful, high-performance browser test client for manual audio testing of the **Pipecat Voice Interview Bot** pipeline.

It connects directly to the WebSocket server running on `ws://localhost:8765`, streams your microphone audio in real-time, and plays back synthesized responses from the bot.

---

## Files Included

*   `index.html` — A premium responsive dark-mode dashboard showing connection indicators, active mic volume meters, and live conversation log messages.
*   `client.js` — Core audio streaming logic that captures mic audio at 16kHz mono, downsamples/serializes it to Int16 PCM binary, manages the non-overlapping audio output playback queue, and handles WebSocket messages.
*   `README.md` — This setup and run guide.

---

## Behind the Scenes: Protocol Details

Rather than relying on complex WebRTC setups, heavy React/Webpack/NPM build pipelines, or protobuf dependencies, this manual client utilizes a custom, ultra-lightweight **JSON/Binary hybrid WebSocket protocol** configured via `JSONSerializer` in `interview_bot.py`:

### **1. Upstream (Browser Client → Pipecat Bot)**
*   **Audio Stream**: Standard raw 16-bit, 16kHz, mono PCM binary audio data sent as raw WebSocket binary frames.
*   **Startup Signal**: Client connects and immediately sends `{"type": "start"}` to trigger the bot's adapter initialization (`on_client_connected`) and play the introductory greeting.
*   **Teardown Signal**: Client sends `{"type": "end"}` to wrap up database/adapter session tracking.

### **2. Downstream (Pipecat Bot → Browser Client)**
*   **Audio Stream**: The server sends binary WAV audio frames (containing WAV headers for simple decoder parsing), which the browser decodes via `AudioContext.decodeAudioData` and plays.
*   **Text & State**: Control frames are sent as JSON string frames:
    *   `{"type": "text", "text": "AI response text here"}` — Used to log transcriptions and AI replies on the page.
    *   `{"type": "end"}` — Clean wrap-up signal from the dialogue adapter.

---

## How to Run & Test

Follow these simple steps to perform manual audio verification:

### **Step 1: Set Your API Keys**
Ensure your API keys are loaded in your terminal:
```powershell
$env:DEEPGRAM_API_KEY="your-deepgram-key"
$env:CARTESIA_API_KEY="your-cartesia-key"
$env:GROQ_API_KEY="your-groq-key"
```

### **Step 2: Start the Pipecat Bot**
Launch the standalone voice layer WebSocket server:
```powershell
venv\Scripts\python.exe backend/pipecat_integration/interview_bot.py
```
*Expected console output:*
```text
2026-05-24 00:18:59,185 - InterviewBot - INFO - Starting Pipecat WebSocket Bot at ws://localhost:8765
2026-05-24 00:18:59,256 - websockets.server - INFO - server listening on 127.0.0.1:8765
```

### **Step 3: Serve the Browser Client**
Modern web browsers require pages using microphone permissions (`getUserMedia`) to be served either over `localhost` or an `https` connection (local file execution `file://` might block mic access in some versions).

To ensure a highly compatible run, serve the page using Python's built-in HTTP server:
1. Open a new terminal in the project root directory.
2. Run:
   ```powershell
   venv\Scripts\python.exe -m http.server 8000
   ```
3. Open your browser and navigate to:
   [http://localhost:8000/backend/pipecat_integration/manual_client/](http://localhost:8000/backend/pipecat_integration/manual_client/)

---

## Manual Verification Steps

1. Click **Connect Mic & Bot**.
2. Allow browser microphone access when prompted.
3. Observe the logs page showing:
   *   `WebSocket connection established successfully.`
   *   `Bot says: "Welcome! ... [Intro Greeting]"`
4. Listen to the introductory question spoken aloud.
5. Speak clearly into your mic:
   *"Hello, I am ready to begin the interview."*
6. Watch the live volume visualizer react to your speech.
7. Confirm that the bot transcribes your answer, processes it through the `InterviewDialogueAdapter` → `DialogueManager`, and speaks back the next follow-up question!
8. Click **Disconnect** when you are ready to conclude and persist report metrics.

---

## Known Limitations

*   **Single active runner**: The `interview_bot.py` is configured with a single active runner, supporting one active WebSocket client session at a time.
*   **WAV Headers**: The browser audio context parses WAV headers on each binary chunk. Gaps in streaming can occur under poor local network connections if chunk latency increases.
