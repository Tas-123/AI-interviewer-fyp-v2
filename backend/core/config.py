"""
Central application configuration.

Loads environment variables once and exposes typed settings for all runtimes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root: AI-interviewer-fyp-v2/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    # Paths
    project_root: Path = PROJECT_ROOT
    log_dir: Path = PROJECT_ROOT / "logs"
    reports_dir: Path = PROJECT_ROOT / "reports"
    aborted_reports_dir: Path = PROJECT_ROOT / "reports" / "aborted"
    live_debug_log: Path = PROJECT_ROOT / "logs" / "live_interview_debug.log"

    # LLM
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_evaluator_model: str = os.getenv("GROQ_EVALUATOR_MODEL", "") or os.getenv(
        "GROQ_MODEL", "llama-3.3-70b-versatile"
    )

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    processor_log_frames: bool = _env_bool("PROCESSOR_LOG_FRAMES", False)

    # Voice providers (Pipecat path)
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-2")
    deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "en")
    deepgram_endpointing_ms: int = int(os.getenv("DEEPGRAM_ENDPOINTING_MS", "500"))
    deepgram_smart_format: bool = _env_bool("DEEPGRAM_SMART_FORMAT", True)
    deepgram_punctuate: bool = _env_bool("DEEPGRAM_PUNCTUATE", True)
    deepgram_keywords: str = os.getenv(
        "DEEPGRAM_KEYWORDS",
        "FastAPI:1,Qdrant:1,Python:1,TensorFlow:1,scikit-learn:1",
    )
    cartesia_api_key: str = os.getenv("CARTESIA_API_KEY", "")
    cartesia_voice_id: str = os.getenv(
        "CARTESIA_VOICE_ID", "2d1cc513-e4d7-466c-bb9a-cb7127e79391"
    )
    pipecat_ws_host: str = os.getenv("PIPECAT_WS_HOST", "localhost")
    pipecat_ws_port: int = int(os.getenv("PIPECAT_WS_PORT", "8765"))
    report_http_port: int = int(os.getenv("REPORT_HTTP_PORT", "8766"))

    # Database
    database_url: str = os.getenv("DATABASE_URL", "")

    # Voice turn timing (used by Pipecat processor; tuned further in Phase 5)
    transcript_debounce_seconds: float = float(
        os.getenv("TRANSCRIPT_DEBOUNCE_SECONDS", "3.0")
    )
    short_answer_grace_seconds: float = float(
        os.getenv("SHORT_ANSWER_GRACE_SECONDS", "2.5")
    )
    short_answer_word_threshold: int = int(os.getenv("SHORT_ANSWER_WORD_THRESHOLD", "6"))
    startup_audio_gate_seconds: float = float(
        os.getenv("STARTUP_AUDIO_GATE_SECONDS", "4.0")
    )
    startup_refresh_seconds: float = float(os.getenv("STARTUP_REFRESH_SECONDS", "3.0"))
    bot_echo_cooldown_seconds: float = float(
        os.getenv("BOT_ECHO_COOLDOWN_SECONDS", "1.2")
    )
    bot_stop_echo_cooldown_seconds: float = float(
        os.getenv("BOT_STOP_ECHO_COOLDOWN_SECONDS", "0.8")
    )
    closing_delay_seconds: float = float(os.getenv("CLOSING_DELAY_SECONDS", "2.5"))
    # Candidate silence after bot finishes speaking (Phase 6)
    candidate_silence_nudge_seconds: float = float(
        os.getenv("CANDIDATE_SILENCE_NUDGE_SECONDS", "8.0")
    )
    candidate_silence_rephrase_seconds: float = float(
        os.getenv("CANDIDATE_SILENCE_REPHRASE_SECONDS", "15.0")
    )
    # Ignore Silero barge-in for this long after bot TTS starts (reduces echo cuts)
    barge_in_min_bot_speak_seconds: float = float(
        os.getenv("BARGE_IN_MIN_BOT_SPEAK_SECONDS", "0.25")
    )
    # Debounce after final STT (interim-only paths may wait longer)
    final_transcript_debounce_seconds: float = float(
        os.getenv("FINAL_TRANSCRIPT_DEBOUNCE_SECONDS", "0.35")
    )

    # Runtime flags
    enable_dev_text_voice_ws: bool = _env_bool("ENABLE_DEV_TEXT_VOICE_WS", False)
    debug_live_logging: bool = _env_bool("DEBUG_LIVE_LOGGING", False)

    def ensure_directories(self) -> None:
        """Create runtime directories if missing."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.aborted_reports_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
