"""
Pipecat Voice-Based Interview Bot.
Assembles the pipeline: WebSocket Input -> Deepgram STT -> InterviewProcessor -> Cartesia TTS -> WebSocket Output.
Runs as a standalone WebSocket server at localhost:8765.
"""

import os
import sys
import asyncio
import logging
import struct
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Ensure backend directory is in path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.config import settings
from pipecat_integration import config
from pipecat_integration.interview_processor import InterviewProcessor, sanitize_tts_text
from integration.dialogue_adapter import InterviewDialogueAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("InterviewBot")

def start_report_http_server(host="localhost", port=None):
    """
    Small local HTTP server for the manual browser client.
    It serves the latest saved report from the reports folder.
    """
    if port is None:
        port = settings.report_http_port
    class ReportHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code, payload):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send_json(200, {"ok": True})

        def do_GET(self):
            if self.path not in ["/latest-report", "/reports/latest"]:
                self._send_json(404, {"error": "Not found"})
                return

            reports_dir = settings.reports_dir
            if not reports_dir.exists():
                self._send_json(404, {"error": "No reports folder found yet"})
                return

            report_files = sorted(
                reports_dir.glob("interview_report_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            if not report_files:
                self._send_json(404, {"error": "No report files found yet"})
                return

            latest = report_files[0]
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                self._send_json(200, {
                    "file": str(latest),
                    "report": data
                })
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def log_message(self, format, *args):
            return

    try:
        server = HTTPServer((host, port), ReportHandler)
    except OSError as exc:
        logger.warning(f"Report HTTP server not started on {host}:{port}: {exc}")
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Report HTTP server running at http://{host}:{port}/latest-report")

async def run_bot():
    """
    Main runner for the Pipecat interview voice bot.
    """
    # 1. Verify API Keys are available in the environment
    if not config.DEEPGRAM_API_KEY or not config.CARTESIA_API_KEY:
        logger.error(
            "API Keys missing! Please set DEEPGRAM_API_KEY and CARTESIA_API_KEY in your environment."
        )
        sys.exit(1)

    start_report_http_server()

    try:
        import numpy as np
        from pipecat.transports.websocket.server import WebsocketServerTransport, WebsocketServerParams
        from pipecat.services.deepgram.stt import DeepgramSTTService
        from pipecat.services.cartesia.tts import CartesiaTTSService
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineTask
        from pipecat.frames.frames import TextFrame, EndFrame, TTSSpeakFrame, ClientConnectedFrame, Frame, OutputAudioRawFrame, InputAudioRawFrame
        from pipecat.serializers.base_serializer import FrameSerializer
        from pipecat.processors.audio.vad_processor import VADProcessor
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams
    except ImportError as e:
        logger.error(
            f"Failed to import Pipecat-ai packages: {e}\n"
            "Please make sure to run: pip install -r requirements-pipecat.txt"
        )
        sys.exit(1)

    # --- Diagnostic VAD Analyzer with lower thresholds for browser mic audio ---
    class DiagnosticSileroVADAnalyzer(SileroVADAnalyzer):
        """
        SileroVADAnalyzer subclass with diagnostic logging.
        Logs audio amplitude, confidence and volume every 20 chunks,
        and logs every VAD state change immediately.
        Uses lower thresholds to be more sensitive to browser mic audio.
        """
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._chunk_count = 0
            self._last_reported_state = None

        async def analyze_audio(self, buffer: bytes):
            self._chunk_count += 1

            # Compute amplitude stats from raw int16 PCM bytes
            if len(buffer) >= 2:
                samples = np.frombuffer(buffer, dtype=np.int16)
                rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                max_amp = int(np.max(np.abs(samples)))
            else:
                rms = 0.0
                max_amp = 0

            # Log every 20 chunks (~every 1 second of audio at 8192-byte chunks)
            if self._chunk_count % 20 == 0:
                logger.info(
                    f"VAD audio chunk #{self._chunk_count}: "
                    f"bytes={len(buffer)}, rms={rms:.1f}, max_amp={max_amp}/32767 "
                    f"(params: confidence≥{self._params.confidence}, min_volume≥{self._params.min_volume})"
                )

            state = await super().analyze_audio(buffer)

            # Log every state change
            if state != self._last_reported_state:
                logger.info(
                    f"VAD state changed: {self._last_reported_state} → {state.name} "
                    f"(chunk #{self._chunk_count}, rms={rms:.1f}, max_amp={max_amp})"
                )
                self._last_reported_state = state

            return state

    class JSONSerializer(FrameSerializer):
        def __init__(self):
            super().__init__()

        async def serialize(self, frame: Frame) -> str | bytes | None:
            if isinstance(frame, OutputAudioRawFrame):
                return frame.audio
            elif isinstance(frame, TTSSpeakFrame):
                import json
                return json.dumps({"type": "text", "text": frame.text})
            elif isinstance(frame, TextFrame):
                import json
                return json.dumps({"type": "text", "text": frame.text})
            elif isinstance(frame, EndFrame):
                import json
                return json.dumps({"type": "end"})
            return None

        async def deserialize(self, data: str | bytes) -> Frame | None:
            if isinstance(data, bytes):
                logger.info(f"deserialize: Received binary audio chunk from browser, length: {len(data)} bytes")
                frame = InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
                logger.info(f"deserialize: Created InputAudioRawFrame: sample_rate={frame.sample_rate}, num_channels={frame.num_channels}")
                return frame
            elif isinstance(data, str):
                import json
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "start":
                        return ClientConnectedFrame()
                    elif msg.get("type") == "end":
                        return EndFrame()
                    elif msg.get("type") == "interrupt":
                        reason = msg.get("reason", "unknown")
                        logger.info(f"SERVER_INTERRUPT_CONTROL_RECEIVED: reason={reason}")
                        return None  # Don't inject a frame; VAD handles once mic audio resumes
                except Exception:
                    pass
            return None

    # 2. Instantiate core dialogue adapter
    adapter = InterviewDialogueAdapter()

    # 3. Setup WebSocket server transport
    logger.info(f"Initializing WebsocketServerTransport on {config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")
    transport = WebsocketServerTransport(
        host=config.WEBSOCKET_HOST,
        port=config.WEBSOCKET_PORT,
        params=WebsocketServerParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=True,
            serializer=JSONSerializer()
        )
    )

    # 4. Initialize AI services
    logger.info("Initializing Speech-to-Text (Deepgram) and Text-to-Speech (Cartesia) services")
    stt_service = DeepgramSTTService(api_key=config.DEEPGRAM_API_KEY)
    tts_service = CartesiaTTSService(
        api_key=config.CARTESIA_API_KEY,
        settings=CartesiaTTSService.Settings(
            voice=config.CARTESIA_VOICE_ID
        )
    )

    # 5. Initialize our custom processor with a placeholder session_id
    # session_id will be dynamically updated when a client connects
    interview_processor = InterviewProcessor(adapter=adapter, session_id="")

    # 6. Assemble Pipecat pipeline
    # Use DiagnosticSileroVADAnalyzer with more sensitive thresholds for browser mic audio.
    # Default thresholds (confidence=0.7, min_volume=0.6) are too strict for browser mic.
    vad_analyzer = DiagnosticSileroVADAnalyzer(
        params=VADParams(
            confidence=0.5,   # lowered from default 0.7
            min_volume=0.1,   # lowered from default 0.6 (browser mic volume is much lower)
        )
    )
    pipeline = Pipeline([
        transport.input(),
        VADProcessor(vad_analyzer=vad_analyzer),
        stt_service,
        interview_processor,
        tts_service,
        transport.output()
    ])

    # 7. Create Pipeline Task and Runner
    task = PipelineTask(pipeline)
    runner = PipelineRunner()

    # Store the active session ID per connection (supporting one active session at a time in this single runner)
    active_sessions = {}

    # Register client connection lifecycle hooks
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, websocket):
        logger.info("New WebSocket audio client connected.")
        
        try:
            # Start a new dialogue session with a default candidate profile
            # In production, this can be customized/passed during handshake
            result = adapter.start_interview(config.DEFAULT_CANDIDATE_PROFILE)
            
            if result.get("error"):
                logger.error(f"Failed to start dialogue session: {result['error']}")
                await task.queue_frames([
                    TTSSpeakFrame("I'm sorry, I failed to start an interview session. Please try reconnecting.")
                ])
                return
                
            session_id = result.get("session_id")
            greeting = result.get("ai_response_text")
            
            # Map session to this connection and update the processor's active session_id
            active_sessions[websocket] = session_id
            interview_processor.session_id = session_id
            
            logger.info(f"Interview session {session_id} successfully started for new connection.")
            
            # Speak the greeting through TTS
            if greeting:
                greeting = sanitize_tts_text(greeting)
                await task.queue_frames([TTSSpeakFrame(greeting)])
                
        except Exception as ex:
            logger.exception("Error in client connection handler")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, websocket):
        session_id = active_sessions.pop(websocket, None)
        if session_id:
            logger.info(f"WebSocket client disconnected. Concluding session: {session_id}")
            try:
                # Wrap up the session, saving final scores/consistency rating/trend to db and cleaning up
                end_res = adapter.end_interview(session_id)
                final_report = end_res.get("final_report", {})

                logger.info(f"Session {session_id} ended status: {end_res.get('status')}")

                if final_report:
                    ws = final_report.get("weighted_score_summary", {})
                    consistency = final_report.get("consistency_rating", {})
                    metadata = final_report.get("interview_metadata", {})

                    logger.info("========== FINAL INTERVIEW REPORT ==========")
                    logger.info(f"Session ID: {session_id}")
                    logger.info(f"Final Hire Signal: {ws.get('final_hire_signal', 'N/A')}")
                    logger.info(f"Average Weighted Score: {ws.get('avg_weighted_overall', 0)}")
                    logger.info(f"Consistency: {consistency.get('consistency_rating', 'N/A')}")
                    logger.info(f"Total Turns: {metadata.get('total_turns', 0)}")
                    logger.info("===========================================")

                    reports_dir = settings.reports_dir
                    reports_dir.mkdir(exist_ok=True)
                    report_path = reports_dir / f"interview_report_{session_id}.json"

                    with report_path.open("w", encoding="utf-8") as f:
                        json.dump(final_report, f, indent=2, ensure_ascii=False)

                    logger.info(f"Full report saved to: {report_path}")
                else:
                    logger.warning(f"No final report returned for session {session_id}")
            except Exception as ex:
                logger.exception(f"Error ending session {session_id} on disconnect")
        else:
            logger.info("WebSocket client disconnected (no active interview session tracked).")

    # Run the event loop for the WebSocket server pipeline
    logger.info(f"Starting Pipecat WebSocket Bot at ws://{config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")
    try:
        await runner.run(task)
    except Exception as ex:
        logger.exception("Unexpected error during bot execution")

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user.")
