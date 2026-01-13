"""Claude Code CLI integration."""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from voice_agent.agents import load_voice_mode_prompt
from voice_agent.memory import get_memory_context

logger = logging.getLogger(__name__)

# Project directory where Claude Code runs from
PROJECT_DIR = Path(__file__).parent.parent.parent
DEFAULT_CONVERSATIONS_DIR = PROJECT_DIR / "conversations"


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
        latest_usage["cache_read_input_tokens"] = usage.get("cache_read_input_tokens", 0)

    session_file.write_text(json.dumps({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "conversation_id": conversation_id,
        "usage": latest_usage
    }))


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
        return f"{input_tokens // 1000}k tokens in context, {cache_pct}% cached. {status}"

    except (json.JSONDecodeError, OSError):
        return "Couldn't read context usage."


def ask_claude(
    prompt: str,
    timeout: int = 120,
    cwd: Path | None = None,
    conversations_dir: Path | None = None,
    agent: str = "default",
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
        agent: The current agent context for memory scoping

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

    # Fetch memory context (semantic + temporal)
    memory_context = get_memory_context(prompt, agent=agent)
    if memory_context:
        voice_mode_prompt = f"{voice_mode_prompt}\n\n{memory_context}"
        logger.debug(f"Injected memory context for agent={agent}")

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
                timeout=timeout,
                cwd=cwd,
            )

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            raise RuntimeError(f"Claude Code failed: {error_msg}")

        response, thinking, new_conversation_id, usage = parse_claude_output(result.stdout)

        # Save conversation ID and usage for future resumption
        if new_conversation_id:
            save_conversation_id(new_conversation_id, usage, conversations_dir)

        return response, thinking

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude Code timed out after {timeout}s")


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
