"""Audio utilities for notification sounds and format conversion."""

import os
import subprocess
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Cache for converted sounds
_sound_cache: dict[str, bytes] = {}

SOUND_EFFECTS_DIR = Path(__file__).parent.parent.parent / "sound-effects"

# Error type to sound mapping
ERROR_SOUNDS: dict[str, str] = {
    "empty_transcription": "crickets",
    "tts_failed": "spongebob-fail",
    "general_error": "mario-died-sound-effect",
    "fatal_error": "jar-jar-this-is-bad",  # Needs manual fix, won't recover on retry
}


def _convert_to_format(input_path: Path, output_format: str, volume: float = 1.0) -> bytes:
    """Convert audio file to specified format using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
    ]

    # Apply volume filter if not 1.0
    if volume != 1.0:
        cmd.extend(["-af", f"volume={volume}"])

    cmd.extend([
        "-c:a", "libopus" if output_format == "ogg" else "libmp3lame",
        "-b:a", "64k" if output_format == "ogg" else "128k",
        "-f", output_format,
        "pipe:1",
    ])

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.decode()}")
    return result.stdout


def _generate_silence(duration_sec: float, output_format: str) -> bytes:
    """Generate silence of specified duration."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-f", "lavfi",
            "-i", f"anullsrc=r=24000:cl=mono",
            "-t", str(duration_sec),
            "-c:a", "libopus" if output_format == "ogg" else "libmp3lame",
            "-b:a", "64k" if output_format == "ogg" else "128k",
            "-f", output_format,
            "pipe:1",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg silence generation failed: {result.stderr.decode()}")
    return result.stdout


def _get_sound(sound_name: str, output_format: str, volume: float = 1.0) -> bytes | None:
    """Get a sound file converted to the specified format."""
    if not sound_name or sound_name.lower() == "none":
        return None

    cache_key = f"{sound_name}:{output_format}:{volume}"
    if cache_key in _sound_cache:
        return _sound_cache[cache_key]

    # Find the sound file (try common extensions)
    sound_path = None
    for ext in [".mp3", ".wav", ".ogg", ".m4a"]:
        candidate = SOUND_EFFECTS_DIR / f"{sound_name}{ext}"
        if candidate.exists():
            sound_path = candidate
            break

    if sound_path is None:
        logger.warning(f"Sound '{sound_name}' not found in {SOUND_EFFECTS_DIR}")
        return None

    logger.info(f"Converting sound: {sound_path} (volume: {volume})")
    converted = _convert_to_format(sound_path, output_format, volume)
    _sound_cache[cache_key] = converted

    return converted


def get_notification_sound(output_format: str = "ogg") -> bytes | None:
    """
    Get the notification sound converted to the specified format.

    Reads NOTIFICATION_SOUND env var for the sound file name (without extension).
    Reads NOTIFICATION_VOLUME env var for volume level (0.0-1.0, default 0.5).
    Returns None if NOTIFICATION_SOUND is empty or 'none'.
    """
    sound_name = os.getenv("NOTIFICATION_SOUND", "super-nintendo-coin")
    volume = float(os.getenv("NOTIFICATION_VOLUME", "0.5"))
    return _get_sound(sound_name, output_format, volume)


def get_error_sound(error_type: str, output_format: str = "ogg") -> bytes | None:
    """
    Get the error sound for a specific error type.

    Error types: empty_transcription, tts_failed, general_error
    """
    sound_name = ERROR_SOUNDS.get(error_type, ERROR_SOUNDS["general_error"])
    return _get_sound(sound_name, output_format)


def prepend_notification(audio_bytes: bytes, audio_format: str) -> bytes:
    """
    Prepend notification sound with silence padding to audio.

    Structure: [0.5s silence] [notification] [0.5s silence] [audio]

    If NOTIFICATION_SOUND is 'none' or empty, returns audio unchanged.
    """
    notification = get_notification_sound(audio_format)

    if notification is None:
        return audio_bytes

    silence_duration = float(os.getenv("NOTIFICATION_SILENCE", "0.5"))

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as notif_file:
        notif_file.write(notification)
        notif_path = notif_file.name

    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as audio_file:
        audio_file.write(audio_bytes)
        audio_path = audio_file.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
                "-i", notif_path,
                "-i", audio_path,
                "-filter_complex",
                f"[0]atrim=0:{silence_duration},aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[s1];"
                f"[0]atrim=0:{silence_duration},aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[s2];"
                f"[1]aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[n];"
                f"[2]aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[a];"
                f"[s1][n][s2][a]concat=n=4:v=0:a=1[out]",
                "-map", "[out]",
                "-c:a", "libopus" if audio_format == "ogg" else "libmp3lame",
                "-b:a", "64k" if audio_format == "ogg" else "128k",
                "-f", audio_format,
                "pipe:1",
            ],
            capture_output=True,
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg concat failed: {result.stderr.decode()}")
            return audio_bytes  # Return original on failure

        return result.stdout

    finally:
        Path(notif_path).unlink(missing_ok=True)
        Path(audio_path).unlink(missing_ok=True)


def get_success_chime(output_format: str = "ogg") -> bytes | None:
    """
    Get just the notification sound for silent command confirmation.

    Returns: [0.5s silence] [notification] [0.5s silence]
    """
    notification = get_notification_sound(output_format)
    if notification is None:
        return None

    silence_duration = float(os.getenv("NOTIFICATION_SILENCE", "0.5"))

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as f:
        f.write(notification)
        notif_path = f.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-i", notif_path,
                "-filter_complex",
                f"[0]atrim=0:{silence_duration},aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[s1];"
                f"[0]atrim=0:{silence_duration},aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[s2];"
                f"[1]aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono[n];"
                f"[s1][n][s2]concat=n=3:v=0:a=1[out]",
                "-map", "[out]",
                "-c:a", "libopus" if output_format == "ogg" else "libmp3lame",
                "-b:a", "64k" if output_format == "ogg" else "128k",
                "-f", output_format,
                "pipe:1",
            ],
            capture_output=True,
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg chime failed: {result.stderr.decode()}")
            return notification

        return result.stdout

    finally:
        Path(notif_path).unlink(missing_ok=True)