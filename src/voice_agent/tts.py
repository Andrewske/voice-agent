"""TTS router with lazy loading and fallback."""

import logging
import os
import subprocess
from typing import Callable, Awaitable

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _convert_audio(audio_bytes: bytes, from_format: str, to_format: str) -> bytes:
    """Convert audio between formats using ffmpeg."""
    if from_format == to_format:
        return audio_bytes

    logger.info(f"Converting audio from {from_format} to {to_format}")

    result = subprocess.run(
        [
            "ffmpeg",
            "-f", from_format,
            "-i", "pipe:0",
            "-c:a", "libopus" if to_format == "ogg" else "libmp3lame",
            "-b:a", "64k" if to_format == "ogg" else "128k",
            "-f", to_format,
            "pipe:1",
        ],
        input=audio_bytes,
        capture_output=True,
    )

    if result.returncode != 0:
        logger.error(f"Audio conversion failed: {result.stderr.decode()}")
        return audio_bytes  # Return original on failure

    return result.stdout

# Type for TTS synthesize functions
SynthesizeFunc = Callable[[str], Awaitable[bytes]]

# Lazy-loaded providers
_primary: SynthesizeFunc | None = None
_fallback: SynthesizeFunc | None = None
_initialized = False


def _init_providers() -> None:
    """Initialize TTS providers based on config."""
    global _primary, _fallback, _initialized

    if _initialized:
        return

    provider_name = os.getenv("TTS_PROVIDER", "kokoro").lower()
    logger.info(f"Initializing TTS with primary provider: {provider_name}")

    # Set up primary provider
    if provider_name == "kokoro":
        try:
            from voice_agent import tts_kokoro
            _primary = tts_kokoro.synthesize
            logger.info("Kokoro TTS loaded as primary")
        except ImportError as e:
            logger.warning(f"Kokoro not available: {e}. Falling back to API.")
            _primary = None
    elif provider_name == "api":
        _primary = None  # Will use fallback directly
    else:
        logger.warning(f"Unknown TTS_PROVIDER '{provider_name}', using API")
        _primary = None

    # Always set up API fallback
    from voice_agent import tts_api
    _fallback = tts_api.synthesize

    # If no primary, use fallback as primary
    if _primary is None:
        _primary = _fallback
        _fallback = None

    _initialized = True


async def synthesize(text: str) -> bytes:
    """
    Convert text to speech.

    Uses primary provider, falls back to API on failure.
    Returns audio bytes in configured AUDIO_OUTPUT_FORMAT.
    """
    _init_providers()

    provider_format = _get_provider_format()
    output_format = get_output_format()
    used_fallback = False

    try:
        if _primary:
            audio = await _primary(text)
    except Exception as e:
        if _fallback:
            logger.warning(f"Primary TTS failed ({e}), using fallback")
            audio = await _fallback(text)
            provider_format = "mp3"  # Fallback is always API which returns MP3
            used_fallback = True
        else:
            raise
    else:
        if audio is None:
            raise RuntimeError("No TTS provider available")

    # Convert to configured output format if needed
    return _convert_audio(audio, provider_format, output_format)


def get_output_format() -> str:
    """Get the configured output audio format."""
    return os.getenv("AUDIO_OUTPUT_FORMAT", "ogg").lower()


def get_audio_media_type() -> str:
    """Get the MIME type for audio output."""
    output_format = get_output_format()
    return "audio/ogg" if output_format == "ogg" else "audio/mpeg"


def _get_provider_format() -> str:
    """Get the native format of the current TTS provider."""
    provider_name = os.getenv("TTS_PROVIDER", "kokoro").lower()

    if provider_name == "kokoro":
        try:
            import kokoro  # noqa: F401
            return "ogg"
        except ImportError:
            pass

    return "mp3"


async def warm_model() -> None:
    """
    Pre-load TTS model without synthesizing.

    Call this during Claude thinking to reduce latency.
    """
    _init_providers()

    provider_name = os.getenv("TTS_PROVIDER", "kokoro").lower()
    if provider_name == "kokoro":
        try:
            from voice_agent import tts_kokoro
            tts_kokoro.load_model()
            logger.info("TTS model warmed")
        except ImportError:
            pass  # Kokoro not installed, nothing to warm


def unload_model() -> None:
    """Unload TTS model to free resources on shutdown."""
    global _primary, _fallback, _initialized

    provider_name = os.getenv("TTS_PROVIDER", "kokoro").lower()
    if provider_name == "kokoro":
        try:
            from voice_agent import tts_kokoro
            tts_kokoro.unload_model()
        except ImportError:
            pass

    _primary = None
    _fallback = None
    _initialized = False
