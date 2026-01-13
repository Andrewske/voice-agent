"""Text-to-speech using Kokoro."""

import io
import os
import logging
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kokoro import KPipeline

logger = logging.getLogger(__name__)

_pipeline: "KPipeline | None" = None


def load_model() -> "KPipeline":
    """Load the Kokoro TTS pipeline. Called once lazily."""
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    from kokoro import KPipeline

    lang_code = os.getenv("KOKORO_LANG", "a")  # 'a' = American English

    logger.info(f"Loading Kokoro TTS (lang={lang_code})...")
    try:
        _pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")
    except Exception as e:
        raise RuntimeError(f"Failed to load Kokoro TTS model: {e}") from e
    logger.info("Kokoro TTS model loaded")

    return _pipeline


def _wav_to_opus(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to Opus using ffmpeg."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", "64k",
            "-f", "ogg",
            "pipe:1",
        ],
        input=wav_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")
    return result.stdout


def unload_model() -> None:
    """Unload Kokoro TTS model to free resources."""
    global _pipeline

    if _pipeline is not None:
        logger.info("Unloading Kokoro TTS model...")
        del _pipeline
        _pipeline = None

        # Force garbage collection to release CUDA/PyTorch memory
        import gc
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


async def synthesize(text: str) -> bytes:
    """
    Convert text to speech using Kokoro.

    Returns: Opus audio bytes (in Ogg container).
    """
    import numpy as np
    import soundfile as sf

    pipeline = load_model()

    voice = os.getenv("KOKORO_VOICE", "af_heart")
    speed = float(os.getenv("KOKORO_SPEED", "1.0"))

    # Generate audio segments
    generator = pipeline(text, voice=voice, speed=speed)

    # Collect all audio segments
    audio_segments: list[bytes] = []
    for _, _, audio in generator:
        audio_segments.append(audio)

    # Concatenate audio arrays
    if not audio_segments:
        raise RuntimeError("Kokoro generated no audio")

    full_audio = np.concatenate(audio_segments)

    # Convert to WAV bytes
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, full_audio, 24000, format="WAV")
    wav_bytes = wav_buffer.getvalue()

    # Convert WAV to Opus
    return _wav_to_opus(wav_bytes)
