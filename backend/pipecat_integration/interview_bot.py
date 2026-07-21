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
from core.logging_config import setup_logging
from pipecat_integration import config
from pipecat_integration.interview_processor import InterviewProcessor, sanitize_tts_text
from pipecat_integration.preamble_copy import PREAMBLE_INSTRUCTION_LINES
from integration.dialogue_adapter import InterviewDialogueAdapter

# Configure logging
setup_logging()
logger = logging.getLogger("InterviewBot")

def start_report_http_server(host="localhost", port=None):
    """
    Small local HTTP server for the manual browser client.
    Serves latest report JSON and matching HTML from the reports folder.
    """
    if port is None:
        port = settings.report_http_port

    def _iter_report_json_paths():
        dirs = [settings.reports_dir, settings.aborted_reports_dir]
        for d in dirs:
            if not d.exists():
                continue
            yield from d.glob("interview_report_*.json")

    def _session_id_from_report_path(path: Path) -> str:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get("report_meta") or {}
            legacy = data.get("interview_metadata") or {}
            return str(meta.get("session_id") or legacy.get("session_id") or "")
        except Exception:
            return ""

    def _latest_report_json_path(session_id: str | None = None):
        report_files = sorted(
            _iter_report_json_paths(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not report_files:
            return None
        wanted = (session_id or "").strip()
        if wanted:
            for path in report_files:
                if _session_id_from_report_path(path) == wanted:
                    return path
        return report_files[0]

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

        def _send_bytes(self, status_code, body: bytes, content_type: str):
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send_json(200, {"ok": True})

        def do_GET(self):
            raw = self.path
            path = raw.split("?", 1)[0]
            query = ""
            if "?" in raw:
                query = raw.split("?", 1)[1]
            params = {}
            if query:
                from urllib.parse import parse_qs

                params = {k: (v[0] if v else "") for k, v in parse_qs(query).items()}
            session_id = (params.get("session_id") or "").strip() or None

            if path in ("/latest-report.html", "/reports/latest.html"):
                latest = _latest_report_json_path(session_id)
                if latest is None:
                    self._send_bytes(
                        404,
                        b"No report files found yet",
                        "text/plain; charset=utf-8",
                    )
                    return
                html_path = latest.with_suffix(".html")
                if not html_path.exists():
                    # Regenerate HTML from JSON if sibling missing (e.g. older runs).
                    try:
                        from reporting.renderers.html_renderer import render_report_html

                        data = json.loads(latest.read_text(encoding="utf-8"))
                        html_body = render_report_html(data).encode("utf-8")
                        html_path.write_text(
                            html_body.decode("utf-8"), encoding="utf-8"
                        )
                    except Exception as exc:
                        self._send_bytes(
                            500,
                            str(exc).encode("utf-8"),
                            "text/plain; charset=utf-8",
                        )
                        return
                else:
                    html_body = html_path.read_bytes()
                self._send_bytes(200, html_body, "text/html; charset=utf-8")
                return

            if path not in ("/latest-report", "/reports/latest"):
                self._send_json(404, {"error": "Not found"})
                return

            latest = _latest_report_json_path(session_id)
            if latest is None:
                if not settings.reports_dir.exists():
                    self._send_json(404, {"error": "No reports folder found yet"})
                else:
                    self._send_json(404, {"error": "No report files found yet"})
                return

            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                html_path = latest.with_suffix(".html")
                base = f"http://{host}:{port}"
                self._send_json(
                    200,
                    {
                        "file": str(latest),
                        "html_file": str(html_path) if html_path.exists() else None,
                        "html_url": f"{base}/latest-report.html",
                        "report": data,
                    },
                )
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
    logger.info(
        f"Report HTTP server running at http://{host}:{port}/latest-report "
        f"and http://{host}:{port}/latest-report.html"
    )

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
        from pipecat.frames.frames import TextFrame, EndFrame, TTSSpeakFrame, ClientConnectedFrame, Frame, OutputAudioRawFrame, InputAudioRawFrame, OutputTransportMessageFrame, OutputTransportMessageUrgentFrame
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
            self.pending_start_payload: dict = {}
            self.processor = None
            self._control_handlers = {}

        def set_control_handlers(self, handlers: dict) -> None:
            self._control_handlers = handlers or {}

        async def serialize(self, frame: Frame) -> str | bytes | None:
            if isinstance(frame, OutputAudioRawFrame):
                return frame.audio
            # Live conversation projection (versioned UI events).
            if isinstance(
                frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)
            ):
                import json

                if self.should_ignore_frame(frame):
                    return None
                return json.dumps(frame.message)
            # Bot chat text is emitted via conversation_event frames, not TTS text frames
            # (avoids fragmented bubbles from word/sentence TextFrames).
            elif isinstance(frame, EndFrame):
                import json
                return json.dumps({"type": "end"})
            return None

        async def deserialize(self, data: str | bytes) -> Frame | None:
            if isinstance(data, bytes):
                logger.debug("deserialize: Received binary audio chunk, length: %d bytes", len(data))
                frame = InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
                logger.debug(
                    "deserialize: InputAudioRawFrame sample_rate=%s num_channels=%s",
                    frame.sample_rate,
                    frame.num_channels,
                )
                return frame
            elif isinstance(data, str):
                import json
                try:
                    msg = json.loads(data)
                    msg_type = msg.get("type")
                    if msg_type == "instructions":
                        handler = self._control_handlers.get("instructions")
                        if handler:
                            asyncio.create_task(handler())
                        return None
                    if msg_type == "start":
                        payload = {k: v for k, v in msg.items() if k != "type"}
                        handler = self._control_handlers.get("start")
                        if handler:
                            asyncio.create_task(handler(payload))
                        return None
                    if msg_type == "end":
                        # Client disconnect should close the WebSocket only.
                        # EndFrame would tear down Deepgram/Cartesia and break the next reconnect.
                        logger.info("Ignoring client end control message (session ends on WebSocket close).")
                        return None
                    if msg_type == "interrupt":
                        reason = msg.get("reason", "unknown")
                        logger.info(f"SERVER_INTERRUPT_CONTROL_RECEIVED: reason={reason}")
                        proc = getattr(self, "processor", None)
                        if proc is not None:
                            await proc.request_client_interrupt(reason)
                        return None
                except Exception:
                    pass
            return None

    # 2. Instantiate core dialogue adapter and serializer
    adapter = InterviewDialogueAdapter()
    json_serializer = JSONSerializer()

    # 3. Setup WebSocket server transport
    logger.info(f"Initializing WebsocketServerTransport on {config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")
    transport = WebsocketServerTransport(
        host=config.WEBSOCKET_HOST,
        port=config.WEBSOCKET_PORT,
        params=WebsocketServerParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=True,
            serializer=json_serializer
        )
    )

    # 4. Initialize AI services
    logger.info("Initializing Speech-to-Text (Deepgram) and Text-to-Speech (Cartesia) services")
    stt_service = DeepgramSTTService(
        api_key=config.DEEPGRAM_API_KEY,
        settings=DeepgramSTTService.Settings(
            model=settings.deepgram_model,
            language=settings.deepgram_language,
            endpointing=settings.deepgram_endpointing_ms,
            smart_format=settings.deepgram_smart_format,
            punctuate=settings.deepgram_punctuate,
            keywords=[
                item.strip()
                for item in settings.deepgram_keywords.split(",")
                if item.strip()
            ]
            or None,
        ),
    )
    tts_service = CartesiaTTSService(
        api_key=config.CARTESIA_API_KEY,
        settings=CartesiaTTSService.Settings(
            voice=config.CARTESIA_VOICE_ID
        )
    )

    # 5. Initialize our custom processor with a placeholder session_id
    # session_id will be dynamically updated when a client connects
    interview_processor = InterviewProcessor(adapter=adapter, session_id="")
    json_serializer.processor = interview_processor

    # 6. Assemble Pipecat pipeline
    # Use DiagnosticSileroVADAnalyzer with more sensitive thresholds for browser mic audio.
    # Default thresholds (confidence=0.7, min_volume=0.6) are too strict for browser mic.
    vad_analyzer = DiagnosticSileroVADAnalyzer(
        params=VADParams(
            confidence=0.30,
            min_volume=0.015,
            start_secs=0.12,
            stop_secs=float(os.getenv("VAD_STOP_SECS", "0.90")),
        )
    )
    pipeline = Pipeline([
        transport.input(),
        VADProcessor(vad_analyzer=vad_analyzer, audio_idle_timeout=2.0),
        stt_service,
        interview_processor,
        tts_service,
        transport.output()
    ])

    # 7. Create Pipeline Task and Runner
    # Disable Pipecat's 5-minute idle shutdown so the bot stays up waiting for clients.
    task = PipelineTask(pipeline, idle_timeout_secs=None)
    runner = PipelineRunner()

    # Store the active session ID per connection (supporting one active session at a time in this single runner)
    active_sessions = {}
    current_websocket = {"ws": None}

    async def speak_preamble_instructions() -> None:
        """Speak fixed instruction lines via the same Cartesia TTS pipeline."""
        if interview_processor.interview_live:
            logger.info("Ignoring instructions — interview already live.")
            return
        if interview_processor.preamble_active:
            logger.info("Preamble already in progress — ignoring duplicate request.")
            return

        interview_processor.preamble_active = True
        interview_processor.interview_live = False
        logger.info(
            "Speaking pre-interview instructions via Cartesia (%d lines).",
            len(PREAMBLE_INSTRUCTION_LINES),
        )
        try:
            for line in PREAMBLE_INSTRUCTION_LINES:
                text = (line or "").strip()
                if not text:
                    continue
                interview_processor.arm_bot_stopped_waiter()
                await task.queue_frames([
                    interview_processor.conversation.frame_for(
                        interview_processor.conversation.message(
                            role="assistant", text=text
                        )
                    ),
                    TTSSpeakFrame(text),
                ])
                await interview_processor.wait_until_bot_stopped()
                await asyncio.sleep(0.15)
            await task.queue_frames([
                interview_processor.conversation.frame_for(
                    interview_processor.conversation.session("instructions_complete")
                ),
            ])
            logger.info("Pre-interview instructions complete.")
        except asyncio.CancelledError:
            logger.info("Pre-interview instructions cancelled.")
            raise
        except Exception:
            logger.exception("Failed while speaking pre-interview instructions")
            try:
                await task.queue_frames([
                    interview_processor.conversation.frame_for(
                        interview_processor.conversation.session("instructions_complete")
                    ),
                ])
            except Exception:
                pass
        finally:
            interview_processor.preamble_active = False

    async def begin_interview(start_payload: dict | None = None) -> None:
        """Start DialogueManager session and speak the real interviewer greeting."""
        start_payload = start_payload or {}
        ws = current_websocket.get("ws")

        interview_processor.preamble_active = False

        if interview_processor.interview_live and interview_processor.session_id:
            logger.info(
                "Interview already live for session %s — ignoring duplicate start.",
                interview_processor.session_id,
            )
            return

        try:
            if start_payload:
                logger.info(
                    "Starting interview with client profile (target_role=%s)",
                    start_payload.get("target_role", "junior_ai_engineer"),
                )
                result = adapter.start_interview(**start_payload)
            else:
                logger.info("Starting interview with default profile (no resume supplied)")
                result = adapter.start_interview()

            if result.get("error"):
                logger.error(f"Failed to start dialogue session: {result['error']}")
                await task.queue_frames([
                    TTSSpeakFrame(
                        "I'm sorry, I failed to start an interview session. Please try reconnecting."
                    )
                ])
                return

            session_id = result.get("session_id")
            greeting = result.get("ai_response_text")

            if ws is not None:
                active_sessions[ws] = session_id
            interview_processor.session_id = session_id
            interview_processor.reset_for_new_session()
            interview_processor.interview_live = True
            interview_processor.preamble_active = False

            logger.info(f"Interview session {session_id} successfully started.")

            if greeting:
                greeting = sanitize_tts_text(greeting)
                await task.queue_frames([
                    interview_processor.conversation.frame_for(
                        interview_processor.conversation.message(
                            role="assistant", text=greeting
                        )
                    ),
                    interview_processor.conversation.frame_for(
                        interview_processor.conversation.session("started")
                    ),
                    TTSSpeakFrame(greeting),
                ])
        except Exception:
            logger.exception("Error beginning interview session")

    json_serializer.set_control_handlers({
        "instructions": speak_preamble_instructions,
        "start": begin_interview,
    })

    # Register client connection lifecycle hooks
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, websocket):
        logger.info("New WebSocket audio client connected (awaiting instructions/start).")
        current_websocket["ws"] = websocket
        interview_processor.reset_for_new_session()
        interview_processor.interview_live = False
        interview_processor.preamble_active = False

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, websocket):
        if current_websocket.get("ws") is websocket:
            current_websocket["ws"] = None
        interview_processor.interview_live = False
        interview_processor.preamble_active = False

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

                    from reporting.persistence import save_interview_report

                    report_path = save_interview_report(final_report)

                    if report_path:
                        logger.info(f"Full report saved to: {report_path}")
                    else:
                        logger.warning(f"No report file written for session {session_id}")
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
