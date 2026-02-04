"""Claude Code CLI integration."""

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from voice_agent.agents import load_voice_mode_prompt

logger = logging.getLogger(__name__)

# Project directory where Claude Code runs from
PROJECT_DIR = Path(__file__).parent.parent.parent
# Default to voice-agent subdirectory for centralized conversations
DEFAULT_CONVERSATIONS_DIR = PROJECT_DIR / "conversations" / "voice-agent"


def _get_session_file(conversations_dir: Path | None = None) -> Path:
    """Get the session file path for a given conversations directory."""
    if conversations_dir is None:
        conversations_dir = DEFAULT_CONVERSATIONS_DIR
    return conversations_dir / ".claude-session.json"


def get_conversation_id(conversations_dir: Path | None = None) -> str | None:
    """Get today's conversation ID if it exists."""
    session_file = _get_session_file(conversations_dir)
    if not session_file.exists():
        return None

    try:
        data = json.loads(session_file.read_text())
        if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
            return data.get("conversation_id")
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_conversation_id(
    conversation_id: str,
    usage: dict[str, int] | None = None,
    conversations_dir: Path | None = None,
) -> None:
    """Save conversation ID with today's date and latest usage stats."""
    session_file = _get_session_file(conversations_dir)
    session_file.parent.mkdir(parents=True, exist_ok=True)

    # Store latest usage (not cumulative) - this represents current context size
    # Each Claude call's input_tokens includes full history + CLAUDE.md + tools
    latest_usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
    if usage:
        latest_usage["input_tokens"] = usage.get("input_tokens", 0)
        latest_usage["output_tokens"] = usage.get("output_tokens", 0)
        latest_usage["cache_read_input_tokens"] = usage.get(
            "cache_read_input_tokens", 0
        )

    session_file.write_text(
        json.dumps(
            {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "conversation_id": conversation_id,
                "usage": latest_usage,
            }
        )
    )


def clear_conversation(conversations_dir: Path | None = None) -> None:
    """Delete session file to start fresh conversation."""
    session_file = _get_session_file(conversations_dir)
    if session_file.exists():
        session_file.unlink()


def get_context_usage(conversations_dir: Path | None = None) -> str:
    """Get a voice-friendly summary of current context size."""
    session_file = _get_session_file(conversations_dir)
    if not session_file.exists():
        return "No active conversation yet."

    try:
        data = json.loads(session_file.read_text())
        if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return "No conversation today yet."

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        cache_tokens = usage.get("cache_read_input_tokens", 0)

        # input_tokens is the full context: CLAUDE.md + tools + conversation history
        # Claude's context window is ~200k tokens
        if input_tokens > 150_000:
            status = "Getting long, consider starting fresh."
        elif input_tokens > 100_000:
            status = "Past halfway, keep an eye on it."
        elif input_tokens > 50_000:
            status = "About a quarter used."
        else:
            status = "Plenty of room."

        # Show how much is cached (cheaper/faster)
        cache_pct = (cache_tokens * 100 // input_tokens) if input_tokens > 0 else 0
        return (
            f"{input_tokens // 1000}k tokens in context, {cache_pct}% cached. {status}"
        )

    except (json.JSONDecodeError, OSError):
        return "Couldn't read context usage."


def ask_claude(
    prompt: str,
    timeout: int = 90,
    cwd: Path | None = None,
    conversations_dir: Path | None = None,
) -> tuple[str, str]:
    """
    Send a prompt to Claude Code CLI and get the response.

    Maintains daily conversation continuity - resumes today's conversation
    or starts fresh if it's a new day.

    Args:
        prompt: The user's message/question
        timeout: Maximum seconds to wait for response
        cwd: Working directory for Claude (determines which CLAUDE.md is loaded)
        conversations_dir: Directory for session files and conversation logs

    Returns:
        Tuple of (response_text, thinking_text).

    Raises:
        RuntimeError: If Claude Code fails or times out.
    """
    # Default to project directory if not specified
    if cwd is None:
        cwd = PROJECT_DIR
    if conversations_dir is None:
        conversations_dir = DEFAULT_CONVERSATIONS_DIR

    # Load voice mode constraints (universal for all voice interactions)
    voice_mode_prompt = load_voice_mode_prompt()

    # Build CLI args - resume if we have today's conversation
    # Use stream-json + verbose to capture thinking blocks
    conversation_id = get_conversation_id(conversations_dir)
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose"]

    # Add voice mode constraints via --append-system-prompt
    if voice_mode_prompt:
        cmd.extend(["--append-system-prompt", voice_mode_prompt])

    # Add context directory (relative to cwd)
    context_dir = cwd / "context"
    if context_dir.exists():
        cmd.extend(["--add-dir", str(context_dir)])

    if conversation_id:
        cmd.extend(["--resume", conversation_id])

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=cwd,
        )

        # If resume failed (stale conversation ID), retry without it
        if result.returncode != 0 and conversation_id:
            clear_conversation(conversations_dir)
            cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose"]
            if voice_mode_prompt:
                cmd.extend(["--append-system-prompt", voice_mode_prompt])
            if context_dir.exists():
                cmd.extend(["--add-dir", str(context_dir)])
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                cwd=cwd,
            )

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            raise RuntimeError(f"Claude Code failed: {error_msg}")

        response, thinking, new_conversation_id, usage = parse_claude_output(
            result.stdout
        )

        # Save conversation ID and usage for future resumption
        if new_conversation_id:
            save_conversation_id(new_conversation_id, usage, conversations_dir)

        return response, thinking

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude Code timed out after {timeout}s")


async def stream_claude(
    prompt: str,
    cwd: Path | None = None,
    conversations_dir: Path | None = None,
    timeout: int | None = None,
) -> AsyncGenerator[tuple[str, str, str], None]:
    """
    Stream Claude response as async generator.

    Args:
        prompt: The user's message/question
        cwd: Working directory for Claude (determines which CLAUDE.md is loaded)
        conversations_dir: Directory for session files and conversation logs
        timeout: Optional total timeout in seconds. None means no timeout.
                 Note: For streaming, timeout applies to the entire operation,
                 not individual chunks. Consider that Claude may take time to think.

    Yields:
        (event_type, content, conversation_id) tuples
        event_type: 'thinking' | 'text' | 'done'
    """
    # Default to project directory if not specified
    if cwd is None:
        cwd = PROJECT_DIR
    if conversations_dir is None:
        conversations_dir = DEFAULT_CONVERSATIONS_DIR

    # Load voice mode constraints (universal for all voice interactions)
    voice_mode_prompt = load_voice_mode_prompt()

    # Build CLI args - resume if we have today's conversation
    conversation_id = get_conversation_id(conversations_dir)
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose"]

    # Add voice mode constraints via --append-system-prompt
    if voice_mode_prompt:
        cmd.extend(["--append-system-prompt", voice_mode_prompt])

    # Add context directory (relative to cwd)
    context_dir = cwd / "context"
    if context_dir.exists():
        cmd.extend(["--add-dir", str(context_dir)])

    if conversation_id:
        cmd.extend(["--resume", conversation_id])

    process = None
    timeout_task = None

    async def kill_on_timeout():
        """Background task to kill process after timeout."""
        await asyncio.sleep(timeout)  # type: ignore[arg-type]
        if process and process.returncode is None:
            process.kill()
            raise asyncio.TimeoutError()

    try:
        # Start subprocess with async I/O
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        # Start timeout watchdog if specified
        if timeout is not None:
            timeout_task = asyncio.create_task(kill_on_timeout())

        # Send prompt to stdin
        if process.stdin:
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()

        # Read stdout line by line
        current_conversation_id = conversation_id
        final_usage = {}

        if process.stdout:
            async for line in process.stdout:
                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)

                    # Extract conversation ID from any message that has it
                    if "session_id" in msg:
                        current_conversation_id = msg["session_id"]

                    # Assistant message - stream thinking and text content
                    if msg.get("type") == "assistant":
                        content = msg.get("message", {}).get("content", [])
                        for block in content:
                            if block.get("type") == "thinking":
                                thinking_text = block.get("thinking", "").strip()
                                if thinking_text:
                                    yield (
                                        "thinking",
                                        thinking_text,
                                        current_conversation_id or "",
                                    )
                            elif block.get("type") == "text":
                                text_content = block.get("text", "").strip()
                                if text_content:
                                    yield (
                                        "text",
                                        text_content,
                                        current_conversation_id or "",
                                    )

                    # Final result object has usage stats
                    elif msg.get("type") == "result":
                        if "usage" in msg:
                            final_usage = msg["usage"]

                except json.JSONDecodeError:
                    continue

        # Wait for process to complete
        await process.wait()

        if process.returncode != 0:
            stderr = await process.stderr.read() if process.stderr else b""
            error_msg = stderr.decode() or "Unknown error"
            raise RuntimeError(f"Claude Code failed: {error_msg}")

        # Save conversation ID and usage for future resumption
        if current_conversation_id:
            save_conversation_id(
                current_conversation_id, final_usage, conversations_dir
            )

        # Signal completion
        yield "done", "", current_conversation_id or ""

    except asyncio.TimeoutError:
        raise RuntimeError(f"Claude Code timed out after {timeout}s")
    except Exception as e:
        logger.exception(f"Error in stream_claude: {e}")
        raise
    finally:
        # Cancel timeout watchdog if still running
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()
        # Ensure process is terminated
        if process and process.returncode is None:
            process.kill()


def parse_claude_output(output: str) -> tuple[str, str, str | None, dict[str, int]]:
    """
    Parse Claude Code JSONL output to extract response, thinking, conversation ID, and usage.

    Claude Code with --output-format stream-json outputs JSONL (one object per line).
    The final line has type="result" with the actual response in "result" field.
    Thinking blocks appear in assistant messages with content type "thinking".

    Returns:
        Tuple of (response_text, thinking_text, conversation_id, usage_stats).
        usage_stats contains: input_tokens, output_tokens, cache_read_input_tokens
    """
    conversation_id = None
    response_text = ""
    thinking_parts: list[str] = []
    usage: dict[str, int] = {}

    try:
        lines = output.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)

                # Extract conversation ID from any message that has it
                if "session_id" in msg:
                    conversation_id = msg["session_id"]

                # Final result object has the response and usage
                if msg.get("type") == "result":
                    result = msg.get("result", "")
                    if result:
                        response_text = result.strip()
                    # Extract usage stats
                    if "usage" in msg:
                        usage = msg["usage"]

                # Assistant message - extract both thinking and text content
                if msg.get("type") == "assistant":
                    content = msg.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "thinking":
                            thinking_text = block.get("thinking", "").strip()
                            if thinking_text:
                                thinking_parts.append(thinking_text)
                        elif block.get("type") == "text" and not response_text:
                            response_text = block.get("text", "").strip()

            except json.JSONDecodeError:
                continue

        if not response_text:
            response_text = output.strip()[:500]

        thinking_combined = "\n\n".join(thinking_parts)
        return response_text, thinking_combined, conversation_id, usage

    except Exception as e:
        return f"I had trouble processing that. Error: {str(e)[:100]}", "", None, {}
