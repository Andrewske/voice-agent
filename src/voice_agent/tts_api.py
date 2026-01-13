"""Text-to-speech using OpenAI API."""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()


async def synthesize(text: str) -> bytes:
    """
    Convert text to speech using OpenAI TTS.

    Returns: MP3 audio bytes.
    Raises: RuntimeError if TTS fails.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    voice = os.getenv("OPENAI_TTS_VOICE", "alloy")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": voice,
                "response_format": "mp3",
            },
            timeout=30.0,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"OpenAI TTS API error: {response.status_code} - {response.text}"
            )

        return response.content
