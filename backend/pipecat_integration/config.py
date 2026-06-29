"""
Configuration module for Pipecat-based voice interview pipeline.
Loads settings and API keys from environment variables.
"""

import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dotenv import load_dotenv

load_dotenv()

from core.config import settings
from core.interviewer_policy import DEFAULT_CANDIDATE_PROFILE

# Re-export for backward compatibility with interview_bot.py imports
DEEPGRAM_API_KEY = settings.deepgram_api_key
CARTESIA_API_KEY = settings.cartesia_api_key
CARTESIA_VOICE_ID = settings.cartesia_voice_id
WEBSOCKET_HOST = settings.pipecat_ws_host
WEBSOCKET_PORT = settings.pipecat_ws_port
DEFAULT_CANDIDATE_PROFILE = DEFAULT_CANDIDATE_PROFILE
