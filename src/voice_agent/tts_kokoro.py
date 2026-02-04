"""Text-to-speech using Kokoro."""

import io
import os
import logging
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kokoro import KPipeline

logger = logging.getLogger(__name__)

_pipelines: dict[str, "KPipeline"] = {}


def _get_lang_code_for_voice(voice: str) -> str:
    """Determine Kokoro lang_code from voice prefix."""
    prefix = voice[:2] if len(voice) >= 2 else "af"
    lang_map = {
        "af": "a",  # American female
        "am": "a",  # American male
        "bf": "b",  # British female
        "bm": "b",  # British male
        "ef": "a",  # English (defaults to American)
        "em": "a",
        "jf": "j",  # Japanese
        "jm": "j",
        "zf": "z",  # Chinese
        "zm": "z",
        "ff": "f",  # French
        "hf": "h",  # Hindi
        "hm": "h",
        "if": "h",  # Indian (uses Hindi model)
        "im": "h",
        "pf": "p",  # Portuguese
        "pm": "p",
    }
    return lang_map.get(prefix, "a")


def load_model(lang_code: str = "a") -> "KPipeline":
    """Load the Kokoro TTS pipeline for a given lang_code. Cached per lang_code."""
    global _pipelines

    if lang_code in _pipelines:
        return _pipelines[lang_code]

    from kokoro import KPipeline

    logger.info(f"Loading Kokoro TTS (lang={lang_code})...")
    try:
        _pipelines[lang_code] = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")
    except Exception as e:
        raise RuntimeError(f"Failed to load Kokoro TTS model: {e}") from e
    logger.info(f"Kokoro TTS model loaded (lang={lang_code})")

    return _pipelines[lang_code]


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
    """Unload all Kokoro TTS models to free resources."""
    global _pipelines

    if _pipelines:
        logger.info(f"Unloading Kokoro TTS models ({len(_pipelines)} pipelines)...")
        _pipelines.clear()

        # Force garbage collection to release CUDA/PyTorch memory
        import gc
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


async def synthesize(text: str, voice: str | None = None) -> bytes:
    """
    Convert text to speech using Kokoro.

    Args:
        text: Text to synthesize
        voice: Optional voice override. Falls back to KOKORO_VOICE env var.

    Returns: Opus audio bytes (in Ogg container).
    """
    import numpy as np
    import soundfile as sf

    voice = voice or os.getenv("KOKORO_VOICE", "af_heart")
    lang_code = _get_lang_code_for_voice(voice)
    pipeline = load_model(lang_code)
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
