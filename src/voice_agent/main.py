"""FastAPI voice agent server."""

import atexit
import json
import signal
import tempfile
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import asyncio

from voice_agent.transcribe import (
    transcribe,
    unload_model as unload_transcribe_model,
    set_hotwords,
)
from voice_agent.claude import ask_claude, clear_conversation, get_context_usage
from voice_agent.tts import (
    synthesize,
    warm_model,
    get_audio_media_type,
    get_output_format,
    unload_model as unload_tts_model,
)
from voice_agent.audio import prepend_notification, get_error_sound, get_success_chime
from voice_agent.agents import (
    load_agents_config,
    extract_keywords_from_window,
    get_command_for_agent,
    load_current_agent,
    save_current_agent,
    save_last_command,
    get_last_command,
    clear_last_command,
)
from voice_agent.commands import execute_command, undo_last


# Pydantic models for API endpoints
class ChatRequest(BaseModel):
    message: str


class AgentSwitchRequest(BaseModel):
    agent: str


# Phrases that trigger conversation reset
RESET_PHRASES = ["new conversation", "start fresh", "reset conversation"]
# Phrases that trigger context usage check
CONTEXT_PHRASES = ["check context", "context usage", "how much context", "token usage"]


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan - cleanup resources on shutdown."""
    yield
    # Shutdown: unload models (may already be done by signal handler)
    _cleanup_models()


app = FastAPI(
    title="Voice Agent",
    description="Claude Code powered voice assistant",
    lifespan=lifespan,
)

# Project directory and default conversations log directory
PROJECT_DIR = Path(__file__).parent.parent.parent
DEFAULT_CONVERSATIONS_DIR = PROJECT_DIR / "conversations"
DEFAULT_CONVERSATIONS_DIR.mkdir(exist_ok=True)

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

            # Get agent path
            if current_agent_name and current_agent_name in CONFIG.agents:
                agent_config = CONFIG.agents[current_agent_name]
                cwd = agent_config.path
                conversations_dir = agent_config.path / "conversations"
            else:
                cwd = PROJECT_DIR
                conversations_dir = DEFAULT_CONVERSATIONS_DIR

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
                            import re

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
                        audio_bytes = await synthesize(last_agent_response)
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
            conversations_dir = agent_config.path / "conversations"
            logger.info(f"Using agent '{current_agent_name}' at {cwd}")
        else:
            cwd = PROJECT_DIR
            conversations_dir = DEFAULT_CONVERSATIONS_DIR

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
            import time

            logger.info("Getting Claude response...")
            start_time = time.time()
            # Pass agent name for memory scoping (None becomes "default")
            agent_for_memory = current_agent_name or "default"
            assistant_text, thinking_text = ask_claude(
                user_text,
                cwd=cwd,
                conversations_dir=conversations_dir,
                agent=agent_for_memory,
            )
            elapsed = time.time() - start_time
            logger.info(f"Claude responded in {elapsed:.1f}s")
            logger.info(f"Response: {assistant_text}")

        # Synthesize speech
        logger.info("Synthesizing speech...")
        try:
            # Strip markdown formatting for spoken output
            import re

            speech_text = re.sub(r"\*+", "", assistant_text)  # Remove asterisks
            speech_text = re.sub(r"_+", "", speech_text)  # Remove underscores
            speech_text = re.sub(r"`+", "", speech_text)  # Remove backticks
            audio_bytes = await synthesize(speech_text)
        except Exception as tts_error:
            # Log full traceback for debugging
            import traceback

            logger.error(f"TTS failed: {tts_error}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")

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
        logger.error(f"Error processing voice ({error_type}): {e}")

        error_sound = get_error_sound(error_type, audio_format)
        if error_sound:
            return Response(content=error_sound, media_type=get_audio_media_type())
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/transcribe")
async def transcribe_only(file: UploadFile) -> dict[str, str]:
    """Debug endpoint: transcribe audio without Claude/TTS."""
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
        conversations_dir = agent_config.path / "conversations"
        agent_for_memory = current_agent_name
    else:
        cwd = PROJECT_DIR
        conversations_dir = DEFAULT_CONVERSATIONS_DIR
        agent_for_memory = "default"

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
                agent=agent_for_memory,
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
            logger.error(f"Error in chat stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/conversations")
async def get_conversations() -> list[dict[str, str]]:
    """Get list of conversations with IDs, dates, and previews."""
    # Load current agent
    current_agent_name = load_current_agent()

    # Get conversations directory
    if current_agent_name and current_agent_name in CONFIG.agents:
        conversations_dir = CONFIG.agents[current_agent_name].path / "conversations"
    else:
        conversations_dir = DEFAULT_CONVERSATIONS_DIR

    conversations = []
    if conversations_dir.exists():
        # Look for session files to get conversation IDs and dates
        for session_file in conversations_dir.glob("*.claude-session.json"):
            try:
                data = json.loads(session_file.read_text())
                conversation_id = data.get("conversation_id")
                date = data.get("date")

                if conversation_id and date:
                    # Get preview from Claude's JSONL conversation file
                    project_hash = (
                        "-home-kevin-coding-voice-agent"  # TODO: make this configurable
                    )
                    jsonl_file = (
                        Path.home()
                        / ".claude"
                        / "projects"
                        / project_hash
                        / "conversations"
                        / f"{conversation_id}.jsonl"
                    )
                    preview = ""
                    if jsonl_file.exists():
                        try:
                            with open(jsonl_file, "r") as f:
                                lines = f.readlines()
                                # Find the last user message
                                for line in reversed(lines):
                                    if line.strip():
                                        msg = json.loads(line)
                                        if msg.get("type") == "user" and msg.get(
                                            "message"
                                        ):
                                            content = msg["message"]
                                            if isinstance(content, list):
                                                # Handle content as list of blocks
                                                for block in content:
                                                    if block.get("type") == "text":
                                                        preview = block.get(
                                                            "text", ""
                                                        ).strip()[:100]
                                                        break
                                            elif isinstance(
                                                content, dict
                                            ) and content.get("content"):
                                                # Handle content as dict
                                                preview = content.get(
                                                    "content", ""
                                                ).strip()[:100]
                                            else:
                                                # Handle content as string
                                                preview = str(content).strip()[:100]
                                            break
                        except (json.JSONDecodeError, OSError):
                            pass

                    conversations.append(
                        {"id": conversation_id, "date": date, "preview": preview}
                    )
            except (json.JSONDecodeError, OSError):
                continue

    # Sort by date descending
    conversations.sort(key=lambda x: x["date"], reverse=True)
    return conversations


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, str | list]:
    """Get full conversation by ID."""
    # Read from Claude's native JSONL format
    project_hash = "-home-kevin-coding-voice-agent"  # TODO: make this configurable
    jsonl_file = (
        Path.home()
        / ".claude"
        / "projects"
        / project_hash
        / "conversations"
        / f"{conversation_id}.jsonl"
    )

    if not jsonl_file.exists():
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
                            # Handle content as list of blocks
                            for block in content:
                                if block.get("type") == "text":
                                    user_text = block.get("text", "").strip()
                                    break
                        elif isinstance(content, dict) and content.get("content"):
                            # Handle content as dict
                            user_text = content.get("content", "").strip()
                        else:
                            # Handle content as string
                            user_text = str(content).strip()

                        if user_text:
                            messages.append({"role": "user", "content": user_text})

                    # Extract assistant messages
                    elif msg.get("type") == "assistant" and msg.get("message"):
                        content = msg["message"]
                        assistant_text = ""
                        thinking_text = ""

                        if isinstance(content, list):
                            # Handle content as list of blocks
                            for block in content:
                                if block.get("type") == "thinking":
                                    thinking_text = block.get("thinking", "").strip()
                                elif block.get("type") == "text":
                                    assistant_text = block.get("text", "").strip()
                        elif isinstance(content, dict):
                            # Handle content as dict
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
