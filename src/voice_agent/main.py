"""FastAPI voice agent server."""

import asyncio
import atexit
import json
import logging
import re
import signal
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from voice_agent.agents import (
    clear_last_command,
    extract_keywords_from_window,
    get_command_for_agent,
    get_last_command,
    load_agents_config,
    load_current_agent,
    save_current_agent,
    save_last_command,
)
from voice_agent.audio import get_error_sound, get_success_chime, prepend_notification
from voice_agent.claude import ask_claude, clear_conversation, get_context_usage
from voice_agent.commands import execute_command, undo_last
from voice_agent.research import spawn_research
from voice_agent.transcribe import (
    set_hotwords,
    transcribe,
)
from voice_agent.transcribe import (
    unload_model as unload_transcribe_model,
)
from voice_agent.tts import (
    get_audio_media_type,
    get_output_format,
    synthesize,
    warm_model,
)
from voice_agent.tts import (
    unload_model as unload_tts_model,
)


# Pydantic models for API endpoints
class ChatRequest(BaseModel):
    message: str


class AgentSwitchRequest(BaseModel):
    agent: str


# Phrases that trigger conversation reset
RESET_PHRASES = []
# Phrases that trigger context usage check
CONTEXT_PHRASES = []


def is_reset_request(text: str) -> bool:
    """Check if user is requesting a conversation reset."""
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in RESET_PHRASES)


def is_context_request(text: str) -> bool:
    """Check if user is requesting context usage info."""
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in CONTEXT_PHRASES)


def is_fatal_error(error: Exception) -> bool:
    """
    Check if an error is fatal (needs manual fix) vs transient (might work on retry).

    Fatal errors: CUDA OOM, model loading failures, missing dependencies
    Transient errors: API timeouts, network issues, temporary failures
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # CUDA/GPU memory errors - need to restart or reduce load
    if "cuda" in error_type.lower() or "outofmemory" in error_type.lower():
        return True
    if "cuda out of memory" in error_str or "out of memory" in error_str:
        return True

    # Model loading failures - missing files, corrupted weights
    if "no such file" in error_str and ("model" in error_str or "weight" in error_str):
        return True
    if "failed to load" in error_str or "could not load" in error_str:
        return True

    # Missing system dependencies
    if isinstance(error, FileNotFoundError):
        if "ffmpeg" in error_str or "claude" in error_str:
            return True

    # Import errors for required packages
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return True

    return False


# Setup logging - both console and file
LOG_FILE = Path(__file__).parent.parent.parent / "voice-agent.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger(__name__)

# Track if cleanup has run to avoid double-cleanup
_cleanup_done = False

# Track last ML model usage for idle unloading
_last_ml_request_time: float = 0.0
_models_loaded = False
ML_IDLE_TIMEOUT = 30 * 60  # 30 minutes in seconds


def _cleanup_models() -> None:
    """Synchronous cleanup for signal/atexit handlers."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    logger.info("Cleaning up models...")
    unload_transcribe_model()
    unload_tts_model()
    logger.info("Models unloaded")


def _signal_handler(signum: int, frame: object) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    _cleanup_models()
    raise SystemExit(0)


# Register cleanup handlers - these run even when uvicorn reloader kills the process
atexit.register(_cleanup_models)
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _unload_if_idle() -> None:
    """Unload models if idle for ML_IDLE_TIMEOUT seconds."""
    global _models_loaded
    if not _models_loaded:
        return
    if _last_ml_request_time == 0:
        return
    idle_time = time.time() - _last_ml_request_time
    if idle_time >= ML_IDLE_TIMEOUT:
        logger.info(f"Models idle for {idle_time / 60:.1f} min, unloading...")
        unload_transcribe_model()
        unload_tts_model()
        _models_loaded = False
        logger.info("Models unloaded due to idle timeout")


def _mark_ml_used() -> None:
    """Mark ML models as recently used."""
    global _last_ml_request_time, _models_loaded
    _last_ml_request_time = time.time()
    _models_loaded = True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan - cleanup resources on shutdown."""

    # Start background task to check for idle model unloading
    async def idle_checker():
        while True:
            await asyncio.sleep(60)  # Check every minute
            _unload_if_idle()

    idle_task = asyncio.create_task(idle_checker())
    try:
        yield
    finally:
        idle_task.cancel()
        # Shutdown: unload models (may already be done by signal handler)
        _cleanup_models()


app = FastAPI(
    title="Voice Agent",
    description="Claude Code powered voice assistant",
    lifespan=lifespan,
)

# Project directory and conversations root
PROJECT_DIR = Path(__file__).parent.parent.parent
CONVERSATIONS_ROOT = PROJECT_DIR / "conversations"
CONVERSATIONS_ROOT.mkdir(exist_ok=True)

# Legacy alias for backward compatibility
DEFAULT_CONVERSATIONS_DIR = CONVERSATIONS_ROOT / "voice-agent"
DEFAULT_CONVERSATIONS_DIR.mkdir(exist_ok=True)


def get_conversations_dir(agent_name: str | None) -> Path:
    """Get the conversations directory for an agent.

    All conversations are centralized under PROJECT_DIR/conversations/{agent-name}/
    """
    if agent_name is None:
        agent_name = "voice-agent"
    conversations_dir = CONVERSATIONS_ROOT / agent_name
    conversations_dir.mkdir(parents=True, exist_ok=True)
    return conversations_dir


def get_claude_project_hash(project_dir: Path) -> str:
    """Compute Claude Code's project hash from a directory path.

    Claude Code uses the absolute path with slashes replaced by dashes.
    Example: /home/kevin/coding/voice-agent -> -home-kevin-coding-voice-agent
    """
    return str(project_dir.resolve()).replace("/", "-")


# Load configuration on startup
CONFIG = load_agents_config()
logger.info(f"Loaded {len(CONFIG.agents)} agents: {list(CONFIG.agents.keys())}")
logger.info(f"Loaded {len(CONFIG.commands)} commands: {list(CONFIG.commands.keys())}")
logger.info(f"Loaded {len(CONFIG.keywords)} keywords for Whisper")

# Set hotwords for transcription
set_hotwords(CONFIG)


def log_conversation(
    user_text: str,
    assistant_text: str,
    thinking_text: str = "",
    conversations_dir: Path | None = None,
    source: str = "",
) -> None:
    """Append conversation to today's log file."""
    if conversations_dir is None:
        conversations_dir = DEFAULT_CONVERSATIONS_DIR

    conversations_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = conversations_dir / f"{today}.md"

    timestamp = datetime.now().strftime("%H:%M")
    marker = f" [{source}]" if source else ""
    entry = f"\n## {timestamp}{marker}\n**Kevin:** {user_text}\n\n"
    if thinking_text:
        entry += f"**Agent thinking:** {thinking_text}\n\n"
    entry += f"**Agent:** {assistant_text}\n"

    with open(log_file, "a") as f:
        f.write(entry)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/voice")
async def process_voice(request: Request) -> Response:
    """
    Process a voice recording and return audio response.

    POST raw audio bytes (m4a, wav, mp3, etc.)
    Returns: Audio response in configured format (default: Opus/ogg)
    """
    _mark_ml_used()
    content = await request.body()
    logger.info(f"Received raw audio: {len(content)} bytes")
    audio_format = get_output_format()

    if len(content) < 100:
        logger.warning("Audio too short")
        error_sound = get_error_sound("empty_transcription", audio_format)
        if error_sound:
            return Response(content=error_sound, media_type=get_audio_media_type())
        raise HTTPException(status_code=400, detail="No audio data received")

    # Detect format from content or default to m4a
    suffix = ".m4a"
    if content[:4] == b"RIFF":
        suffix = ".wav"
    elif content[:3] == b"ID3" or content[:2] == b"\xff\xfb":
        suffix = ".mp3"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info("Transcribing audio...")
        user_text = transcribe(tmp_path)
        logger.info(f"Transcription: {user_text}")

        # Start warming TTS model while Claude thinks
        asyncio.create_task(warm_model())

        # Empty transcription - just play crickets, no TTS needed
        if not user_text.strip():
            logger.warning("Empty transcription")
            error_sound = get_error_sound("empty_transcription", audio_format)
            if error_sound:
                return Response(content=error_sound, media_type=get_audio_media_type())
            raise HTTPException(status_code=400, detail="Could not transcribe audio")

        # Load current agent (sticky routing)
        current_agent_name = load_current_agent()

        # Extract keywords from first 5 words
        extraction = extract_keywords_from_window(user_text, CONFIG)

        if extraction["has_agent_keyword"]:
            # Agent command mode
            new_agent_name = extraction["agent_name"]
            command_name = extraction["command"]
            message = extraction["message"]

            # Switch agent if specified (or to default if None)
            if new_agent_name != current_agent_name:
                save_current_agent(new_agent_name)
                current_agent_name = new_agent_name
                logger.info(f"Switched to agent: {new_agent_name or 'default'}")

            # Get agent path and voice
            if current_agent_name and current_agent_name in CONFIG.agents:
                agent_config = CONFIG.agents[current_agent_name]
                cwd = agent_config.path
                agent_voice = agent_config.voice
            else:
                cwd = PROJECT_DIR
                agent_voice = None
            conversations_dir = get_conversations_dir(current_agent_name)

            # Handle commands
            if command_name:
                cmd_config = get_command_for_agent(
                    command_name, current_agent_name, CONFIG
                )

                if cmd_config is None:
                    # Command not available for this agent - return crickets
                    logger.warning(
                        f"Command '{command_name}' not available for agent '{current_agent_name}'"
                    )
                    error_sound = get_error_sound("empty_transcription", audio_format)
                    if error_sound:
                        return Response(
                            content=error_sound, media_type=get_audio_media_type()
                        )

                # Handle special commands
                if command_name == "undo":
                    last = get_last_command()
                    if last:
                        undo_last(
                            last["command"], Path(last.get("agent_path", str(cwd)))
                        )
                        clear_last_command()
                    chime = get_success_chime(audio_format)
                    if chime:
                        log_conversation(user_text, "[undo]", "", conversations_dir)
                        return Response(
                            content=chime, media_type=get_audio_media_type()
                        )

                elif command_name == "repeat":
                    # Find last agent response from conversation log
                    today = datetime.now().strftime("%Y-%m-%d")
                    log_file = conversations_dir / f"{today}.md"

                    last_agent_response = None
                    if log_file.exists():
                        with open(log_file, "r") as f:
                            content = f.read()
                            # Find all "**Agent:**" entries
                            matches = list(
                                re.finditer(
                                    r"\*\*Agent:\*\* (.+?)(?=\n## |\n\*\*Agent thinking:\*\*|\Z)",
                                    content,
                                    re.DOTALL,
                                )
                            )
                            if matches:
                                last_agent_response = matches[-1].group(1).strip()

                    if last_agent_response:
                        # Convert text to speech and return
                        audio_bytes = await synthesize(
                            last_agent_response, voice=agent_voice
                        )
                        audio_bytes = prepend_notification(audio_bytes, audio_format)
                        log_conversation(user_text, "[repeated]", "", conversations_dir)
                        return Response(
                            content=audio_bytes, media_type=get_audio_media_type()
                        )
                    else:
                        # Nothing to repeat - crickets
                        error_sound = get_error_sound(
                            "empty_transcription", audio_format
                        )
                        if error_sound:
                            return Response(
                                content=error_sound, media_type=get_audio_media_type()
                            )

                elif command_name == "research":
                    # Fire-and-forget research subprocess
                    # Generate topic slug from message (already stripped of "research" keyword)
                    # Take first 5 words, kebab-case, alphanumeric only
                    words = message.lower().split()[:5]
                    topic_slug = "-".join(words)
                    topic_slug = "".join(
                        c if c.isalnum() or c == "-" else "" for c in topic_slug
                    )
                    topic_slug = topic_slug.strip("-")  # Remove leading/trailing dashes

                    # Output goes to current agent's research folder
                    output_dir = cwd / "research"

                    output_file = spawn_research(message, output_dir, topic_slug)

                    assistant_text = f"Started research on {message}. Results will be saved to {output_file.name}"

                    # Synthesize speech for the response
                    audio_bytes = await synthesize(assistant_text, voice=agent_voice)
                    audio_bytes = prepend_notification(audio_bytes, audio_format)
                    log_conversation(user_text, assistant_text, "", conversations_dir)
                    return Response(
                        content=audio_bytes, media_type=get_audio_media_type()
                    )

                else:
                    # Regular command (log, listen, etc.)
                    if not message.strip():
                        # No message provided - return crickets
                        logger.warning(f"Command '{command_name}' with no message")
                        error_sound = get_error_sound(
                            "empty_transcription", audio_format
                        )
                        if error_sound:
                            return Response(
                                content=error_sound, media_type=get_audio_media_type()
                            )

                    # Execute the command
                    success = execute_command(command_name, message, cwd)

                    if success and cmd_config and cmd_config.silent:
                        # Save for undo/repeat
                        save_last_command(
                            current_agent_name, command_name, message, cwd
                        )
                        # Return just the chime
                        chime = get_success_chime(audio_format)
                        if chime:
                            log_conversation(
                                user_text, f"[{command_name}]", "", conversations_dir
                            )
                            return Response(
                                content=chime, media_type=get_audio_media_type()
                            )
                        # Silent command succeeded but no chime available - return empty response
                        log_conversation(
                            user_text, f"[{command_name}]", "", conversations_dir
                        )
                        return Response(content=b"", media_type=get_audio_media_type())

                    # Non-silent command or failed - continue to Claude
                    user_text = message

            else:
                # No command, just agent switch - use remaining text
                user_text = message if message else user_text

        # Get active agent config for Claude
        if current_agent_name and current_agent_name in CONFIG.agents:
            agent_config = CONFIG.agents[current_agent_name]
            cwd = agent_config.path
            agent_voice = agent_config.voice  # Per-agent TTS voice
            logger.info(f"Using agent '{current_agent_name}' at {cwd}")
        else:
            cwd = PROJECT_DIR
            agent_voice = None
        conversations_dir = get_conversations_dir(current_agent_name)

        # Check for special commands (reset, context)
        thinking_text = ""
        if is_reset_request(user_text):
            logger.info("Resetting conversation...")
            clear_conversation(conversations_dir)
            assistant_text = "Starting a new conversation."
        elif is_context_request(user_text):
            logger.info("Checking context usage...")
            assistant_text = get_context_usage(conversations_dir)
        elif not user_text.strip():
            # Handle case where trigger phrase was the entire message
            assistant_text = "I'm here. What would you like to discuss?"
        else:
            logger.info("Getting Claude response...")
            start_time = time.time()
            assistant_text, thinking_text = ask_claude(
                user_text,
                cwd=cwd,
                conversations_dir=conversations_dir,
            )
            elapsed = time.time() - start_time
            logger.info(f"Claude responded in {elapsed:.1f}s")
            logger.info(f"Response: {assistant_text}")

        # Synthesize speech
        logger.info("Synthesizing speech...")
        try:
            # Strip markdown formatting for spoken output
            speech_text = re.sub(r"\*+", "", assistant_text)  # Remove asterisks
            speech_text = re.sub(r"_+", "", speech_text)  # Remove underscores
            speech_text = re.sub(r"`+", "", speech_text)  # Remove backticks
            audio_bytes = await synthesize(speech_text, voice=agent_voice)
        except Exception as tts_error:
            # Log full traceback for debugging
            logger.exception(f"TTS failed: {tts_error}")

            # Fatal TTS errors (model load failure) vs transient (API timeout)
            error_type = "fatal_error" if is_fatal_error(tts_error) else "tts_failed"
            error_sound = get_error_sound(error_type, audio_format)
            if error_sound:
                return Response(content=error_sound, media_type=get_audio_media_type())
            raise

        # Add notification sound
        audio_bytes = prepend_notification(audio_bytes, audio_format)

        log_conversation(user_text, assistant_text, thinking_text, conversations_dir)

        return Response(content=audio_bytes, media_type=get_audio_media_type())

    except Exception as e:
        # Determine if this is a fatal error (needs manual fix) or transient
        error_type = "fatal_error" if is_fatal_error(e) else "general_error"
        logger.exception(f"Error processing voice ({error_type}): {e}")

        error_sound = get_error_sound(error_type, audio_format)
        if error_sound:
            return Response(content=error_sound, media_type=get_audio_media_type())
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/transcribe")
async def transcribe_only(file: UploadFile) -> dict[str, str]:
    """Debug endpoint: transcribe audio without Claude/TTS."""
    _mark_ml_used()
    suffix = Path(file.filename or "audio.m4a").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = transcribe(tmp_path)
        return {"text": text}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/tts")
async def tts_only(text: str) -> Response:
    """Debug endpoint: generate speech without transcription/Claude."""
    _mark_ml_used()
    audio_bytes = await synthesize(text)
    return Response(content=audio_bytes, media_type=get_audio_media_type())


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Stream Claude chat response via SSE."""
    from voice_agent.claude import stream_claude

    # Load current agent
    current_agent_name = load_current_agent()

    # Get agent config
    if current_agent_name and current_agent_name in CONFIG.agents:
        agent_config = CONFIG.agents[current_agent_name]
        cwd = agent_config.path
    else:
        cwd = PROJECT_DIR
    conversations_dir = get_conversations_dir(current_agent_name)

    # Collect full response for logging
    full_response = []
    full_thinking = []
    final_conversation_id = ""

    async def generate_events():
        """Generate SSE events from Claude stream."""
        nonlocal final_conversation_id
        try:
            async for event_type, content, conversation_id in stream_claude(
                request.message,
                cwd=cwd,
                conversations_dir=conversations_dir,
            ):
                if event_type == "thinking":
                    full_thinking.append(content)
                    yield f"event: {event_type}\ndata: {json.dumps({'content': content, 'conversation_id': conversation_id})}\n\n"
                elif event_type == "text":
                    full_response.append(content)
                    yield f"event: {event_type}\ndata: {json.dumps({'content': content, 'conversation_id': conversation_id})}\n\n"
                elif event_type == "done":
                    final_conversation_id = conversation_id
                    # Log the complete conversation
                    log_conversation(
                        request.message,
                        "\n".join(full_response),
                        "\n".join(full_thinking),
                        conversations_dir,
                        source="chat",
                    )
                    yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"
        except Exception as e:
            logger.exception(f"Error in chat stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/chat/audio")
async def chat_audio(file: UploadFile) -> StreamingResponse:
    """Stream Claude chat response from audio file via SSE."""
    from voice_agent.claude import stream_claude

    _mark_ml_used()

    # Validate file type
    allowed_extensions = {".m4a", ".mp3", ".wav", ".ogg", ".webm"}
    file_ext = Path(file.filename or "audio.m4a").suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Validate file size (max 25MB)
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 25MB.",
        )

    # Save to temp file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # Transcribe audio
        transcribed_text = transcribe(tmp_path)

        # Check if transcription is empty
        if not transcribed_text or not transcribed_text.strip():
            async def error_event():
                yield f"event: error\ndata: {json.dumps({'content': 'Could not transcribe audio - the recording may be silent or too short'})}\n\n"
            return StreamingResponse(
                error_event(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        # Load current agent
        current_agent_name = load_current_agent()

        # Get agent config
        if current_agent_name and current_agent_name in CONFIG.agents:
            agent_config = CONFIG.agents[current_agent_name]
            cwd = agent_config.path
        else:
            cwd = PROJECT_DIR
        conversations_dir = get_conversations_dir(current_agent_name)

        # Collect full response for logging
        full_response = []
        full_thinking = []

        async def generate_events():
            """Generate SSE events from transcription and Claude stream."""
            try:
                # Send transcription event
                yield f"event: transcription\ndata: {json.dumps({'content': transcribed_text})}\n\n"

                # Stream Claude response
                async for event_type, content, conversation_id in stream_claude(
                    transcribed_text,
                    cwd=cwd,
                    conversations_dir=conversations_dir,
                ):
                    if event_type == "thinking":
                        full_thinking.append(content)
                        yield f"event: {event_type}\ndata: {json.dumps({'content': content, 'conversation_id': conversation_id})}\n\n"
                    elif event_type == "text":
                        full_response.append(content)
                        yield f"event: {event_type}\ndata: {json.dumps({'content': content, 'conversation_id': conversation_id})}\n\n"
                    elif event_type == "done":
                        # Log the complete conversation
                        log_conversation(
                            transcribed_text,
                            "\n".join(full_response),
                            "\n".join(full_thinking),
                            conversations_dir,
                            source="audio",
                        )
                        yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"
            except Exception as e:
                logger.exception(f"Error in audio chat stream: {e}")
                yield f"event: error\ndata: {json.dumps({'content': str(e)})}\n\n"

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    finally:
        # Clean up temp file
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


def get_preview_from_markdown(md_file: Path, max_length: int = 100) -> str:
    """Extract last user message from markdown conversation log."""
    if not md_file.exists():
        return ""
    try:
        content = md_file.read_text()
        # Find all user messages: **Kevin:** ...
        matches = re.findall(
            r"\*\*Kevin:\*\* (.+?)(?:\n\n|\n\*\*|$)", content, re.DOTALL
        )
        if matches:
            return matches[-1].strip()[:max_length]
    except OSError:
        pass
    return ""


@app.get("/api/conversations")
async def get_conversations() -> list[dict[str, str]]:
    """Get list of conversations with IDs, dates, and previews."""
    # Load current agent
    current_agent_name = load_current_agent()
    conversations_dir = get_conversations_dir(current_agent_name)

    conversations = []
    if conversations_dir.exists():
        # List all markdown files matching date pattern (YYYY-MM-DD.md)
        for md_file in conversations_dir.glob("????-??-??.md"):
            date = md_file.stem  # e.g., "2026-01-31"
            preview = get_preview_from_markdown(md_file)

            # Use date as ID for historical conversations
            # Check if there's a session file with Claude conversation ID
            conversation_id = date
            session_file = conversations_dir / ".claude-session.json"
            if session_file.exists():
                try:
                    data = json.loads(session_file.read_text())
                    if data.get("date") == date:
                        conversation_id = data.get("conversation_id", date)
                except (json.JSONDecodeError, OSError):
                    pass

            conversations.append(
                {
                    "id": conversation_id,
                    "date": date,
                    "preview": preview,
                    "agent": current_agent_name or "voice-agent",
                }
            )

    # Sort by date descending
    conversations.sort(key=lambda x: x["date"], reverse=True)
    return conversations


def parse_markdown_with_timestamps(md_file: Path) -> list[dict]:
    """Parse markdown conversation log into messages with timestamps."""
    messages = []
    if not md_file.exists():
        return messages

    date_str = md_file.stem  # e.g., "2026-01-31"

    try:
        content = md_file.read_text()
        # Split by ## timestamp headers and capture the timestamp
        parts = re.split(r"^## (\d{1,2}:\d{2}).*$", content, flags=re.MULTILINE)

        # parts[0] is before first header, then alternating: timestamp, content
        i = 1
        while i < len(parts) - 1:
            timestamp = parts[i]  # e.g., "14:30"
            section = parts[i + 1]
            i += 2

            if not section.strip():
                continue

            # Create ISO timestamp for sorting
            iso_timestamp = f"{date_str}T{timestamp}:00"

            # Extract user message
            user_match = re.search(
                r"\*\*Kevin:\*\* (.+?)(?=\n\n\*\*Agent|\n\*\*Agent|\Z)",
                section,
                re.DOTALL,
            )
            if user_match:
                messages.append(
                    {
                        "role": "user",
                        "content": user_match.group(1).strip(),
                        "timestamp": timestamp,
                        "iso_timestamp": iso_timestamp,
                    }
                )

            # Extract thinking (optional)
            thinking_text = ""
            thinking_match = re.search(
                r"\*\*Agent thinking:\*\* (.+?)(?=\n\n\*\*Agent:\*\*|\n\*\*Agent:\*\*|\Z)",
                section,
                re.DOTALL,
            )
            if thinking_match:
                thinking_text = thinking_match.group(1).strip()

            # Extract agent response
            agent_match = re.search(
                r"\*\*Agent:\*\* (.+?)(?=\n\n## |\n## |\Z)", section, re.DOTALL
            )
            if agent_match:
                messages.append(
                    {
                        "role": "assistant",
                        "content": agent_match.group(1).strip(),
                        "thinking": thinking_text,
                        "timestamp": timestamp,
                        "iso_timestamp": iso_timestamp,
                    }
                )
    except OSError:
        pass

    return messages


@app.get("/api/conversations/recent")
async def get_recent_messages(days: int = 3) -> dict[str, list]:
    """Get messages from the last N days merged together."""
    from datetime import timedelta

    current_agent_name = load_current_agent()
    conversations_dir = get_conversations_dir(current_agent_name)

    all_messages = []
    today = datetime.now().date()

    # Collect messages from last N days
    for i in range(days):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")
        md_file = conversations_dir / f"{date_str}.md"

        if md_file.exists():
            messages = parse_markdown_with_timestamps(md_file)
            all_messages.extend(messages)

    # Sort by iso_timestamp (oldest first so newest at bottom)
    all_messages.sort(key=lambda x: x.get("iso_timestamp", ""))

    # Remove iso_timestamp from output (used only for sorting)
    for msg in all_messages:
        msg.pop("iso_timestamp", None)

    return {"messages": all_messages}


def parse_markdown_conversation(md_file: Path) -> list[dict]:
    """Parse markdown conversation log into messages."""
    messages = []
    if not md_file.exists():
        return messages

    try:
        content = md_file.read_text()
        # Split by ## timestamp headers
        sections = re.split(r"^## \d{1,2}:\d{2}.*$", content, flags=re.MULTILINE)

        for section in sections:
            if not section.strip():
                continue

            # Extract user message
            user_match = re.search(
                r"\*\*Kevin:\*\* (.+?)(?=\n\n\*\*Agent|\n\*\*Agent|\Z)",
                section,
                re.DOTALL,
            )
            if user_match:
                messages.append(
                    {"role": "user", "content": user_match.group(1).strip()}
                )

            # Extract agent response
            agent_match = re.search(
                r"\*\*Agent:\*\* (.+?)(?=\n\n## |\n## |\Z)", section, re.DOTALL
            )
            if agent_match:
                messages.append(
                    {
                        "role": "assistant",
                        "content": agent_match.group(1).strip(),
                        "thinking": "",
                    }
                )
    except OSError:
        pass

    return messages


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, str | list]:
    """Get full conversation by ID (date or UUID)."""
    current_agent_name = load_current_agent()
    conversations_dir = get_conversations_dir(current_agent_name)

    # Check if ID is a date (YYYY-MM-DD format)
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if date_pattern.match(conversation_id):
        # Load from markdown file
        md_file = conversations_dir / f"{conversation_id}.md"
        if md_file.exists():
            messages = parse_markdown_conversation(md_file)
            return {"id": conversation_id, "messages": messages}
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Otherwise try Claude's native JSONL format (for UUID-based IDs)
    project_hash = get_claude_project_hash(PROJECT_DIR)
    jsonl_file = (
        Path.home()
        / ".claude"
        / "projects"
        / project_hash
        / "conversations"
        / f"{conversation_id}.jsonl"
    )

    if not jsonl_file.exists():
        # Try finding by date in session file
        session_file = conversations_dir / ".claude-session.json"
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text())
                if data.get("conversation_id") == conversation_id:
                    date = data.get("date")
                    md_file = conversations_dir / f"{date}.md"
                    if md_file.exists():
                        messages = parse_markdown_conversation(md_file)
                        return {"id": conversation_id, "messages": messages}
            except (json.JSONDecodeError, OSError):
                pass
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = []
    try:
        with open(jsonl_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)

                    # Extract user messages
                    if msg.get("type") == "user" and msg.get("message"):
                        content = msg["message"]
                        user_text = ""
                        if isinstance(content, list):
                            for block in content:
                                if block.get("type") == "text":
                                    user_text = block.get("text", "").strip()
                                    break
                        elif isinstance(content, dict) and content.get("content"):
                            user_text = content.get("content", "").strip()
                        else:
                            user_text = str(content).strip()

                        if user_text:
                            messages.append({"role": "user", "content": user_text})

                    # Extract assistant messages
                    elif msg.get("type") == "assistant" and msg.get("message"):
                        content = msg["message"]
                        assistant_text = ""
                        thinking_text = ""

                        if isinstance(content, list):
                            for block in content:
                                if block.get("type") == "thinking":
                                    thinking_text = block.get("thinking", "").strip()
                                elif block.get("type") == "text":
                                    assistant_text = block.get("text", "").strip()
                        elif isinstance(content, dict):
                            assistant_text = content.get("content", "").strip()

                        if assistant_text or thinking_text:
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": assistant_text,
                                    "thinking": thinking_text,
                                }
                            )

                except json.JSONDecodeError:
                    continue

    except OSError:
        raise HTTPException(status_code=500, detail="Error reading conversation")

    return {"id": conversation_id, "messages": messages}


@app.get("/api/agents")
async def get_agents() -> list[dict[str, str | bool]]:
    """Get list of agents with active status."""
    current_agent = load_current_agent()
    agents = []

    for name, config in CONFIG.agents.items():
        agents.append({"name": name, "active": name == current_agent})

    # Add default agent
    agents.append({"name": "default", "active": current_agent is None})

    return agents


@app.post("/api/agents/switch")
async def switch_agent(request: AgentSwitchRequest) -> dict[str, str]:
    """Switch active agent."""
    agent_name = request.agent

    # Validate agent exists
    if agent_name != "default" and agent_name not in CONFIG.agents:
        raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' not found")

    # Switch agent
    save_current_agent(agent_name if agent_name != "default" else None)

    return {"message": f"Switched to agent '{agent_name}'"}


@app.post("/reload-config")
async def reload_config() -> dict:
    """Reload configuration from voice-agent-config.yaml."""
    global CONFIG
    try:
        CONFIG = load_agents_config()
        set_hotwords(CONFIG)
        return {
            "status": "ok",
            "agents": len(CONFIG.agents),
            "commands": len(CONFIG.commands),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reload config: {str(e)}"
        )


# Static file serving for chat UI (must come after all API routes)
CHAT_UI_DIR = Path(__file__).parent.parent.parent / "chat-ui" / "dist"

if CHAT_UI_DIR.exists():
    # Mount static assets with explicit path
    app.mount("/assets", StaticFiles(directory=CHAT_UI_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str = "") -> FileResponse:
        """Serve React SPA for all non-API routes."""
        return FileResponse(CHAT_UI_DIR / "index.html")
else:
    logging.warning(
        f"Chat UI directory not found at {CHAT_UI_DIR}. Skipping static file serving."
    )
