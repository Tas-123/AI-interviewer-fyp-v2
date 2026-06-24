"""
Streaming Response Handler — Splits AI responses into streamable chunks.

Simulates word-level streaming output for future TTS integration.
Returns async generator of response chunks ready for WebSocket delivery.
"""

import asyncio


# Default configuration
DEFAULT_CHUNK_SIZE = 3     # words per chunk
DEFAULT_DELAY_MS = 50      # milliseconds between chunks


async def stream_response(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    delay_ms: int = DEFAULT_DELAY_MS,
):
    """
    Stream a text response as word-level chunks.

    Yields dicts suitable for direct WebSocket JSON delivery.
    Future TTS systems will consume these chunks for real-time synthesis.

    Args:
        text: full response text to stream
        chunk_size: number of words per chunk
        delay_ms: delay between chunks in milliseconds

    Yields:
        {"type": "ai_response_chunk", "text": "partial text", "is_final": bool}
    """
    if not text:
        yield {
            "type": "ai_response_chunk",
            "text": "",
            "is_final": True,
        }
        return

    words = text.split()
    total_chunks = (len(words) + chunk_size - 1) // chunk_size

    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        chunk_index = i // chunk_size
        is_final = (chunk_index == total_chunks - 1)

        yield {
            "type": "ai_response_chunk",
            "text": chunk_text,
            "is_final": is_final,
        }

        if not is_final and delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)


def split_response_sync(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[dict]:
    """
    Synchronous version of stream_response for testing.

    Args:
        text: full response text
        chunk_size: words per chunk

    Returns:
        List of chunk dicts.
    """
    if not text:
        return [{"type": "ai_response_chunk", "text": "", "is_final": True}]

    words = text.split()
    chunks = []
    total_chunks = (len(words) + chunk_size - 1) // chunk_size

    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        chunk_index = i // chunk_size
        is_final = (chunk_index == total_chunks - 1)

        chunks.append({
            "type": "ai_response_chunk",
            "text": chunk_text,
            "is_final": is_final,
        })

    return chunks
