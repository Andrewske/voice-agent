"""Command handlers for voice agent actions."""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Global voice-commands directory (fallback)
GLOBAL_COMMANDS_DIR = Path(__file__).parent.parent.parent / "voice-commands"


def load_command_prompt(command: str, agent_path: Path) -> str | None:
    """
    Load command prompt from voice-commands directory.

    Lookup order:
    1. Agent's voice-commands/{command}.md
    2. Global voice-commands/{command}.md

    Returns:
        Prompt text if found, None otherwise
    """
    # Check agent-specific first
    agent_cmd_file = agent_path / "voice-commands" / f"{command}.md"
    if agent_cmd_file.exists():
        logger.info(f"Loading command prompt from {agent_cmd_file}")
        return agent_cmd_file.read_text()

    # Fall back to global
    global_cmd_file = GLOBAL_COMMANDS_DIR / f"{command}.md"
    if global_cmd_file.exists():
        logger.info(f"Loading command prompt from {global_cmd_file}")
        return global_cmd_file.read_text()

    logger.warning(f"No command prompt found for '{command}'")
    return None


def execute_command(command: str, message: str, agent_path: Path) -> bool:
    """
    Execute a voice command by calling Claude with the command prompt.

    Args:
        command: Command name (e.g., "log", "listen")
        message: User's message content
        agent_path: Path to the agent directory

    Returns:
        True if successful, False otherwise
    """
    # Load the command prompt
    command_prompt = load_command_prompt(command, agent_path)
    if command_prompt is None:
        logger.error(f"No prompt found for command '{command}'")
        return False

    try:
        # Call Claude with the command prompt
        # Use --append-system-prompt to inject command instructions
        # Run in agent's directory so Claude has access to the right files
        cmd = [
            "claude", "-p",
            "--append-system-prompt", command_prompt,
            "--dangerously-skip-permissions",  # Silent commands shouldn't prompt
        ]

        logger.info(f"Executing command '{command}' via Claude")
        result = subprocess.run(
            cmd,
            input=message,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=agent_path,
        )

        if result.returncode != 0:
            logger.error(f"Claude command failed: {result.stderr}")
            return False

        logger.info(f"Command '{command}' executed successfully")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"Command '{command}' timed out")
        return False
    except Exception as e:
        logger.error(f"Command '{command}' failed: {e}")
        return False


def undo_last(command: str, agent_path: Path) -> bool:
    """
    Undo the last command of the given type.

    Note: Undo is handled locally, not via Claude, because it needs
    to remove the last entry regardless of its content.

    Returns:
        True if undo succeeded, False otherwise
    """
    if command == "log":
        return _undo_last_food_entry(agent_path)
    elif command in ("listen", "note"):
        return _undo_last_note(agent_path)
    else:
        logger.warning(f"Cannot undo command: {command}")
        return False


def _undo_last_food_entry(agent_path: Path) -> bool:
    """Remove last line from current month's food journal."""
    journal_dir = agent_path / "food-journal"
    now = datetime.now()
    journal_file = journal_dir / f"{now.strftime('%Y-%m')}.jsonl"

    if not journal_file.exists():
        logger.warning("No food journal to undo")
        return False

    lines = journal_file.read_text().strip().split("\n")
    if not lines or lines == [""]:
        logger.warning("Food journal is empty")
        return False

    # Remove last line
    remaining = lines[:-1]
    if remaining:
        journal_file.write_text("\n".join(remaining) + "\n")
    else:
        journal_file.write_text("")

    logger.info("Undid last food entry")
    return True


def _undo_last_note(agent_path: Path) -> bool:
    """Remove last note entry from notes.md."""
    notes_file = agent_path / "notes.md"

    if not notes_file.exists():
        logger.warning("No notes to undo")
        return False

    content = notes_file.read_text()

    # Find and remove last ## section
    pattern = r"\n## \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n[^#]*$"
    match = re.search(pattern, content)

    if not match:
        logger.warning("No note entry found to undo")
        return False

    new_content = content[: match.start()]
    notes_file.write_text(new_content)

    logger.info("Undid last note")
    return True
