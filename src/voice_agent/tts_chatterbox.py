"""Text-to-speech using Chatterbox (voice cloning)."""

import io
import os
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatterbox.tts import ChatterboxTTS

logger = logging.getLogger(__name__)

_model: "ChatterboxTTS | None" = None

# Project root for resolving relative voice paths
PROJECT_ROOT = Path(__file__).parent.parent.parent


def load_model() -> "ChatterboxTTS":
    """Load the Chatterbox TTS model. Called once lazily."""
    global _model

    if _model is not None:
        return _model

    from chatterbox.tts import ChatterboxTTS

    device = os.getenv("CHATTERBOX_DEVICE", "cuda")

    logger.info(f"Loading Chatterbox TTS (device={device})...")
    try:
        _model = ChatterboxTTS.from_pretrained(device=device)
    except Exception as e:
        raise RuntimeError(f"Failed to load Chatterbox TTS model: {e}") from e
    logger.info("Chatterbox TTS model loaded")

    return _model


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


def _get_voice_path() -> Path:
    """Get the path to the voice reference file."""
    voice_path = os.getenv("CHATTERBOX_VOICE", "voices/theo.wav")

    path = Path(voice_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / voice_path

    if not path.exists():
        raise RuntimeError(f"Voice reference file not found: {path}")

    return path


def unload_model() -> None:
    """Unload Chatterbox TTS model to free resources."""
    global _model

    if _model is not None:
        logger.info("Unloading Chatterbox TTS model...")
        del _model
        _model = None

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
    Convert text to speech using Chatterbox with voice cloning.

    Returns: Opus audio bytes (in Ogg container).
    """
    import torchaudio

    model = load_model()
    voice_path = _get_voice_path()

    logger.info(f"Generating speech with voice: {voice_path.name}")

    # Generate audio with voice cloning
    wav_tensor = model.generate(
        text,
        audio_prompt_path=str(voice_path),
    )

    # Convert tensor to WAV bytes
    wav_buffer = io.BytesIO()
    torchaudio.save(wav_buffer, wav_tensor, model.sr, format="wav")
    wav_bytes = wav_buffer.getvalue()

    # Convert WAV to Opus
    return _wav_to_opus(wav_bytes)
