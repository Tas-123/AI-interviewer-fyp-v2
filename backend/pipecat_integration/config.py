"""
Configuration module for Pipecat-based voice interview pipeline.
Loads settings and API keys from environment variables.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# API Keys
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")

# LLM API key if dialogue manager needs it directly
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Voice configuration (Cartesia default voice ID: 'Barack Obama' / 'News Anchor' style or a default)
# Cartesia's default English male voice or generic helpful voice ID
# Let's use a widely known default male voice (e.g. 248be419-c632-4f23-aaf1-08ec32a0db4a for 'Barack Obama'
# or a pleasant British male voice like 2d1cc513-e4d7-466c-bb9a-cb7127e79391)
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID", "2d1cc513-e4d7-466c-bb9a-cb7127e79391")

# WebSocket server transport settings
# Defaults to localhost:8765 to avoid conflicting with the main FastAPI backend (usually 8000)
WEBSOCKET_HOST = os.getenv("PIPECAT_WS_HOST", "localhost")
WEBSOCKET_PORT = int(os.getenv("PIPECAT_WS_PORT", "8765"))

# Fallback default candidate profile for direct test connections
DEFAULT_CANDIDATE_PROFILE = {
    "name": "Candidate",
    "role": "AI Engineer",
    "skills": [
        "Python",
        "Machine Learning",
        "Deep Learning",
        "NLP",
        "APIs",
        "Data Preprocessing",
        "Model Evaluation"
    ],
    "experience": (
        "Entry-level to junior AI engineer with project experience in Python, "
        "machine learning, deep learning, NLP, APIs, and AI applications."
    )
}

class PipecatConfig:
    DEEPGRAM_API_KEY = DEEPGRAM_API_KEY
    CARTESIA_API_KEY = CARTESIA_API_KEY
    GEMINI_API_KEY = GEMINI_API_KEY
    CARTESIA_VOICE_ID = CARTESIA_VOICE_ID
    WEBSOCKET_HOST = WEBSOCKET_HOST
    WEBSOCKET_PORT = WEBSOCKET_PORT
    DEFAULT_CANDIDATE_PROFILE = DEFAULT_CANDIDATE_PROFILE

