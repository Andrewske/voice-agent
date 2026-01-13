"""Audio transcription using Whisper (OpenAI or faster-whisper)."""

import os
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    import whisper
    from faster_whisper import WhisperModel

from voice_agent.agents import VoiceAgentConfig

load_dotenv()

logger = logging.getLogger(__name__)

# Lazy-loaded models
_openai_model: "whisper.Whisper | None" = None
_faster_model: "WhisperModel | None" = None

# Cached hotwords string
_hotwords: str | None = None


def build_hotwords_string(config: VoiceAgentConfig) -> str:
    """
    Build hotwords string from config for Whisper.

    Includes: keywords, command names, aliases, agent names
    """
    words: set[str] = set()

    # Add keywords
    for kw in config.keywords:
        # Split multi-word keywords
        words.update(kw.lower().split())

    # Add command names and aliases
    for cmd in config.commands.values():
        words.add(cmd.name.lower())
        for alias in cmd.aliases:
            words.add(alias.lower())

    # Add agent names (split hyphenated)
    for agent in config.agents.values():
        for part in agent.name.replace("-", " ").split():
            words.add(part.lower())

    return " ".join(sorted(words))


def set_hotwords(config: VoiceAgentConfig) -> None:
    """Set hotwords from config (call on startup)."""
    global _hotwords
    _hotwords = build_hotwords_string(config)
    logger.info(f"Whisper hotwords: {_hotwords}")


def get_hotwords() -> str | None:
    """Get the cached hotwords string."""
    return _hotwords


def _get_openai_model() -> "whisper.Whisper":
    """Get or load the OpenAI Whisper model."""
    global _openai_model

    if _openai_model is not None:
        return _openai_model

    import whisper
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_name = os.getenv("WHISPER_MODEL", "base.en")

    logger.info(f"Loading OpenAI Whisper model '{model_name}' on {device}...")
    try:
        _openai_model = whisper.load_model(model_name, device=device)
    except Exception as e:
        raise RuntimeError(f"Failed to load Whisper model '{model_name}': {e}") from e
    logger.info("OpenAI Whisper model loaded")

    return _openai_model


def _get_faster_model() -> "WhisperModel":
    """Get or load the faster-whisper model."""
    global _faster_model

    if _faster_model is not None:
        return _faster_model

    from faster_whisper import WhisperModel

    model_name = os.getenv("WHISPER_MODEL", "base.en")
    device = os.getenv("WHISPER_DEVICE", "cuda")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")

    logger.info(f"Loading faster-whisper model '{model_name}' on {device}...")
    try:
        _faster_model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as e:
        raise RuntimeError(f"Failed to load faster-whisper model '{model_name}': {e}") from e
    logger.info("faster-whisper model loaded")

    return _faster_model


def _transcribe_openai(audio_path: str | Path) -> str:
    """Transcribe using OpenAI Whisper."""
    model = _get_openai_model()
    result = model.transcribe(str(audio_path), fp16=False)
    return result["text"].strip()


def _transcribe_faster(audio_path: str | Path) -> str:
    """Transcribe using faster-whisper with hotwords."""
    model = _get_faster_model()

    # Use hotwords if available
    hotwords = get_hotwords()
    segments, _ = model.transcribe(
        str(audio_path),
        hotwords=hotwords,
    )
    return " ".join(seg.text for seg in segments).strip()


def transcribe(audio_path: str | Path) -> str:
    """
    Transcribe an audio file to text.

    Uses TRANSCRIBE_PROVIDER env var to select backend:
    - 'local' or 'faster' (default): faster-whisper
    - 'openai': OpenAI Whisper

    Args:
        audio_path: Path to the audio file (.m4a, .wav, .mp3, etc.)

    Returns:
        Transcribed text string.
    """
    provider = os.getenv("TRANSCRIBE_PROVIDER", "local").lower()

    if provider == "openai":
        return _transcribe_openai(audio_path)

    # Default: try faster-whisper, fall back to OpenAI
    try:
        return _transcribe_faster(audio_path)
    except ImportError as e:
        logger.warning(f"faster-whisper not available: {e}. Falling back to OpenAI.")
        return _transcribe_openai(audio_path)


def warm_model() -> None:
    """Pre-load the transcription model."""
    provider = os.getenv("TRANSCRIBE_PROVIDER", "local").lower()

    if provider == "openai":
        _get_openai_model()
        return

    # Default: try faster-whisper, fall back to OpenAI
    try:
        _get_faster_model()
    except ImportError:
        _get_openai_model()


def unload_model() -> None:
    """Unload transcription models to free resources."""
    global _openai_model, _faster_model

    if _faster_model is not None:
        logger.info("Unloading faster-whisper model...")
        del _faster_model
        _faster_model = None

    if _openai_model is not None:
        logger.info("Unloading OpenAI Whisper model...")
        del _openai_model
        _openai_model = None

    # Force garbage collection to release CUDA memory
    import gc
    gc.collect()

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
