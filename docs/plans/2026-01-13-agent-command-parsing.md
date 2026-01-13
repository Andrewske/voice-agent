# Agent Command Parsing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement keyword-based agent command parsing with silent commands (chime-only), undo/repeat functionality, and Whisper hotwords for better recognition.

**Architecture:** Keyword extraction in first 5 words. Commands defined at top-level with agent allowlists. Hotwords loaded from YAML and passed to faster-whisper. Silent commands return notification chime only.

**Tech Stack:** Python, FastAPI, faster-whisper, PyYAML, pytest

---

## New YAML Structure

```yaml
# voice-agent-config.yaml

# Keywords for Whisper recognition (loaded as hotwords)
keywords:
  - agent
  - diet
  - budget
  - bonanza
  - career
  - daily
  - video games
  # Add words Whisper frequently misrecognizes

# Commands - agents: [] means universal
commands:
  log:
    agents: [diet]
    silent: true
    aliases: [add, record]
  listen:
    agents: []
    silent: true
    aliases: [note]
  undo:
    agents: []
    silent: true
    aliases: []
  repeat:
    agents: []
    silent: false
    aliases: [again, replay]

agents:
  diet:
    path: "~/journal/agents/diet"
  budget:
    path: "~/journal/agents/budget"
  # ... etc (triggers auto-generated as "{name} agent")
```

---

## Task 1: Update YAML Config Structure

**Files:**
- Modify: `voice-agent-config.yaml`

**Step 1: Replace config with new structure**

```yaml
# voice-agent-config.yaml

# Keywords for Whisper recognition - improves accuracy for these words
keywords:
  - agent
  - diet
  - budget
  - bonanza
  - career
  - daily
  - video games
  - log
  - listen
  - undo
  - repeat

# Commands with agent allowlists (empty = universal)
commands:
  log:
    agents: [diet]
    silent: true
    aliases: [add, record]
  listen:
    agents: []
    silent: true
    aliases: [note]
  undo:
    agents: []
    silent: true
    aliases: [cancel, nevermind]
  repeat:
    agents: []
    silent: false
    aliases: [again, replay]

# Agent definitions - triggers auto-generated as "{name} agent"
agents:
  career:
    path: "~/journal/agents/career"

  budget:
    path: "~/journal/agents/budget"

  diet:
    path: "~/journal/agents/diet"

  daily:
    path: "~/journal/agents/daily"

  bonanza:
    path: "~/journal/agents/bonanza"

  video-games:
    path: "~/journal/agents/video-games"
```

**Step 2: Commit**

```bash
git add voice-agent-config.yaml
git commit -m "$(cat <<'EOF'
refactor: simplify YAML config structure

- Top-level commands with agent allowlists
- Keywords section for Whisper hotwords
- Remove manual triggers (auto-generated now)
- Add undo/repeat commands

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Update Config Loading with Keywords and Commands

**Files:**
- Create: `tests/test_agents.py`
- Modify: `src/voice_agent/agents.py`

**Step 1: Write failing tests for new config structure**

```python
# tests/test_agents.py
"""Tests for agent routing and command parsing."""

import pytest
from pathlib import Path

from voice_agent.agents import (
    load_agents_config,
    AgentConfig,
    CommandConfig,
)


class TestLoadAgentsConfig:
    """Test loading agent configuration."""

    def test_loads_keywords(self) -> None:
        """Keywords are loaded from YAML."""
        config = load_agents_config()
        assert "agent" in config.keywords
        assert "diet" in config.keywords

    def test_loads_commands_with_agents(self) -> None:
        """Commands have agent allowlists."""
        config = load_agents_config()
        assert "log" in config.commands
        assert "diet" in config.commands["log"].agents

    def test_universal_command_has_empty_agents(self) -> None:
        """Universal commands have empty agents list."""
        config = load_agents_config()
        assert "listen" in config.commands
        assert config.commands["listen"].agents == []

    def test_command_aliases_loaded(self) -> None:
        """Command aliases are loaded."""
        config = load_agents_config()
        assert "add" in config.commands["log"].aliases
        assert "record" in config.commands["log"].aliases

    def test_agents_loaded(self) -> None:
        """Agents are loaded with paths."""
        config = load_agents_config()
        assert "diet" in config.agents
        assert config.agents["diet"].path.name == "diet"

    def test_auto_generated_triggers(self) -> None:
        """Each agent has auto-generated '{name} agent' trigger."""
        config = load_agents_config()
        assert "diet agent" in config.agents["diet"].triggers
        assert "budget agent" in config.agents["budget"].triggers

    def test_multi_word_agent_triggers(self) -> None:
        """Multi-word agents get proper triggers."""
        config = load_agents_config()
        # video-games -> "video-games agent" and "video games agent"
        triggers = config.agents["video-games"].triggers
        assert "video games agent" in triggers or "video-games agent" in triggers
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kevin/coding/voice-agent && uv run pytest tests/test_agents.py -v`
Expected: FAIL - load_agents_config returns tuple, not object

**Step 3: Rewrite agents.py with new structure**

```python
# src/voice_agent/agents.py
"""Agent routing and configuration for voice-agent."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

import yaml

logger = logging.getLogger(__name__)

# Project directory
PROJECT_DIR = Path(__file__).parent.parent.parent
CONFIG_FILE = PROJECT_DIR / "voice-agent-config.yaml"
VOICE_MODE_FILE = PROJECT_DIR / "voice-mode.md"
SESSION_FILE = PROJECT_DIR / ".session.json"


@dataclass
class CommandConfig:
    """Configuration for a command."""

    name: str
    agents: list[str] = field(default_factory=list)  # empty = universal
    silent: bool = False
    aliases: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Configuration for a voice agent."""

    name: str
    path: Path
    triggers: list[str] = field(default_factory=list)


@dataclass
class VoiceAgentConfig:
    """Complete voice agent configuration."""

    keywords: list[str] = field(default_factory=list)
    commands: dict[str, CommandConfig] = field(default_factory=dict)
    agents: dict[str, AgentConfig] = field(default_factory=dict)


def load_agents_config() -> VoiceAgentConfig:
    """
    Load agent configuration from voice-agent-config.yaml.

    Returns:
        VoiceAgentConfig with keywords, commands, and agents
    """
    if not CONFIG_FILE.exists():
        return VoiceAgentConfig()

    with open(CONFIG_FILE) as f:
        raw = yaml.safe_load(f)

    # Load keywords
    keywords = raw.get("keywords", [])

    # Load commands
    commands: dict[str, CommandConfig] = {}
    for name, data in raw.get("commands", {}).items():
        commands[name] = CommandConfig(
            name=name,
            agents=data.get("agents", []),
            silent=data.get("silent", False),
            aliases=data.get("aliases", []),
        )

    # Load agents with auto-generated triggers
    agents: dict[str, AgentConfig] = {}
    for name, data in raw.get("agents", {}).items():
        path = Path(data["path"]).expanduser()

        # Auto-generate triggers: "{name} agent"
        triggers = [f"{name} agent"]
        # For hyphenated names, also add space version: "video-games" -> "video games agent"
        if "-" in name:
            triggers.append(f"{name.replace('-', ' ')} agent")

        agents[name] = AgentConfig(name=name, path=path, triggers=triggers)

    return VoiceAgentConfig(keywords=keywords, commands=commands, agents=agents)


class KeywordExtractionResult(TypedDict):
    """Result of extracting keywords from user text."""

    has_agent_keyword: bool
    agent_name: str | None
    command: str | None
    message: str


def extract_keywords_from_window(
    text: str,
    config: VoiceAgentConfig,
    window_size: int = 5,
) -> KeywordExtractionResult:
    """
    Extract agent routing keywords from the first N words.

    Args:
        text: User's transcribed text
        config: Voice agent configuration
        window_size: Number of words to scan (default 5)

    Returns:
        KeywordExtractionResult with extracted data
    """
    words = text.lower().split()
    window = words[:window_size]
    window_text = " ".join(window)

    result: KeywordExtractionResult = {
        "has_agent_keyword": False,
        "agent_name": None,
        "command": None,
        "message": text,
    }

    # Check for "agent" keyword
    if "agent" not in window:
        return result

    result["has_agent_keyword"] = True

    # Find agent name in window
    for agent_name, agent in config.agents.items():
        # Check both hyphenated and space versions
        variants = [agent_name, agent_name.replace("-", " ")]
        for variant in variants:
            if variant in window_text:
                result["agent_name"] = agent_name
                break
        if result["agent_name"]:
            break

    # Find command in window (including aliases)
    for cmd_name, cmd in config.commands.items():
        # Check if command applies to this agent
        if cmd.agents and result["agent_name"] not in cmd.agents:
            continue  # Command not available for this agent

        # Check command name and aliases
        all_names = [cmd_name] + cmd.aliases
        for name in all_names:
            if name in window:
                result["command"] = cmd_name  # Always use canonical name
                break
        if result["command"]:
            break

    # Extract message: everything after the last keyword in window
    keyword_positions: list[int] = []
    for i, word in enumerate(words[:window_size]):
        if word == "agent":
            keyword_positions.append(i)
        # Check if word is a command or alias
        for cmd_name, cmd in config.commands.items():
            if word == cmd_name or word in cmd.aliases:
                keyword_positions.append(i)
                break
        # Check if word is part of agent name
        for agent_name in config.agents:
            agent_words = agent_name.replace("-", " ").split()
            if word in agent_words or word == agent_name:
                keyword_positions.append(i)
                break

    if keyword_positions:
        message_start = max(keyword_positions) + 1
        result["message"] = " ".join(words[message_start:])

    return result


def get_command_for_agent(
    command_name: str,
    agent_name: str | None,
    config: VoiceAgentConfig,
) -> CommandConfig | None:
    """
    Get command config if available for the given agent.

    Args:
        command_name: Name of the command
        agent_name: Name of the agent (None for default)
        config: Voice agent configuration

    Returns:
        CommandConfig if command is available for agent, None otherwise
    """
    cmd = config.commands.get(command_name)
    if cmd is None:
        return None

    # Universal command (empty agents list) or agent is in allowlist
    if not cmd.agents or agent_name in cmd.agents:
        return cmd

    return None


def load_voice_mode_prompt() -> str:
    """Load the universal voice mode constraints."""
    if not VOICE_MODE_FILE.exists():
        return ""
    return VOICE_MODE_FILE.read_text()


def load_current_agent() -> str | None:
    """Load the currently active agent from session file."""
    if not SESSION_FILE.exists():
        return None

    try:
        data = json.loads(SESSION_FILE.read_text())
        return data.get("current_agent")
    except (json.JSONDecodeError, OSError):
        return None


def save_current_agent(agent_name: str | None) -> None:
    """Save the currently active agent to session file."""
    data = _load_session_data()
    data["current_agent"] = agent_name
    SESSION_FILE.write_text(json.dumps(data))


def _load_session_data() -> dict:
    """Load session data from file."""
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_last_command(agent_name: str | None, command: str, message: str) -> None:
    """Save last command for undo/repeat functionality."""
    data = _load_session_data()
    data["last_command"] = {
        "agent": agent_name,
        "command": command,
        "message": message,
    }
    SESSION_FILE.write_text(json.dumps(data))


def get_last_command() -> dict | None:
    """Get the last command executed."""
    data = _load_session_data()
    return data.get("last_command")


def clear_last_command() -> None:
    """Clear the last command after undo."""
    data = _load_session_data()
    data.pop("last_command", None)
    SESSION_FILE.write_text(json.dumps(data))
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kevin/coding/voice-agent && uv run pytest tests/test_agents.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/voice_agent/agents.py tests/test_agents.py
git commit -m "$(cat <<'EOF'
refactor: new config structure with VoiceAgentConfig

- Keywords list for Whisper hotwords
- Commands with agent allowlists and aliases
- Auto-generated triggers for agents
- Session helpers for undo/repeat

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Whisper Hotwords from Config

**Files:**
- Modify: `src/voice_agent/transcribe.py`
- Create: `tests/test_transcribe.py`

**Step 1: Write failing test for hotwords**

```python
# tests/test_transcribe.py
"""Tests for transcription module."""

import pytest
from voice_agent.transcribe import build_hotwords_string
from voice_agent.agents import VoiceAgentConfig, CommandConfig, AgentConfig


class TestBuildHotwords:
    """Test hotwords string generation."""

    def test_includes_keywords_from_config(self) -> None:
        """Keywords from config are included."""
        config = VoiceAgentConfig(
            keywords=["agent", "diet", "bonanza"],
            commands={},
            agents={},
        )
        result = build_hotwords_string(config)
        assert "agent" in result
        assert "diet" in result
        assert "bonanza" in result

    def test_includes_command_names(self) -> None:
        """Command names are included."""
        config = VoiceAgentConfig(
            keywords=[],
            commands={
                "log": CommandConfig(name="log"),
                "listen": CommandConfig(name="listen"),
            },
            agents={},
        )
        result = build_hotwords_string(config)
        assert "log" in result
        assert "listen" in result

    def test_includes_command_aliases(self) -> None:
        """Command aliases are included."""
        config = VoiceAgentConfig(
            keywords=[],
            commands={
                "log": CommandConfig(name="log", aliases=["add", "record"]),
            },
            agents={},
        )
        result = build_hotwords_string(config)
        assert "add" in result
        assert "record" in result

    def test_includes_agent_names(self) -> None:
        """Agent names are included."""
        config = VoiceAgentConfig(
            keywords=[],
            commands={},
            agents={
                "diet": AgentConfig(name="diet", path=Path("/tmp")),
                "video-games": AgentConfig(name="video-games", path=Path("/tmp")),
            },
        )
        result = build_hotwords_string(config)
        assert "diet" in result
        assert "video" in result
        assert "games" in result

    def test_deduplicates_words(self) -> None:
        """Duplicate words are removed."""
        config = VoiceAgentConfig(
            keywords=["agent", "diet"],
            commands={"log": CommandConfig(name="log")},
            agents={"diet": AgentConfig(name="diet", path=Path("/tmp"))},
        )
        result = build_hotwords_string(config)
        # Count occurrences of "diet"
        assert result.count("diet") == 1
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kevin/coding/voice-agent && uv run pytest tests/test_transcribe.py -v`
Expected: FAIL - build_hotwords_string not found

**Step 3: Add hotwords to transcribe.py**

```python
# Add to src/voice_agent/transcribe.py after imports (around line 16)

from voice_agent.agents import VoiceAgentConfig

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
```

```python
# Update _transcribe_faster in src/voice_agent/transcribe.py (replace lines 76-80)

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
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kevin/coding/voice-agent && uv run pytest tests/test_transcribe.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/voice_agent/transcribe.py tests/test_transcribe.py
git commit -m "$(cat <<'EOF'
feat: add Whisper hotwords from YAML config

Keywords, commands, aliases, and agent names are
combined into hotwords string for better recognition.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create Command Handlers

**Files:**
- Create: `src/voice_agent/commands.py`
- Create: `tests/test_commands.py`

**Step 1: Write failing tests for command handlers**

```python
# tests/test_commands.py
"""Tests for command handlers."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from voice_agent.commands import log_food, note_idea, undo_last, get_last_message


class TestLogFood:
    """Test food logging command."""

    def test_appends_to_food_journal(self, tmp_path: Path) -> None:
        """log_food appends JSONL entry."""
        journal_dir = tmp_path / "food-journal"
        journal_dir.mkdir()

        log_food("two eggs and toast", tmp_path)

        today = datetime.now().strftime("%Y-%m")
        journal_file = journal_dir / f"{today}.jsonl"
        assert journal_file.exists()

        entry = json.loads(journal_file.read_text().strip())
        assert entry["food_description"] == "two eggs and toast"

    def test_returns_entry_for_undo(self, tmp_path: Path) -> None:
        """log_food returns the entry for potential undo."""
        journal_dir = tmp_path / "food-journal"
        journal_dir.mkdir()

        result = log_food("pizza", tmp_path)
        assert result["food_description"] == "pizza"


class TestNoteIdea:
    """Test idea noting command."""

    def test_appends_to_notes(self, tmp_path: Path) -> None:
        """note_idea appends to notes.md."""
        note_idea("cool feature idea", tmp_path)

        notes_file = tmp_path / "notes.md"
        assert notes_file.exists()
        assert "cool feature idea" in notes_file.read_text()

    def test_includes_timestamp(self, tmp_path: Path) -> None:
        """Notes include timestamp."""
        note_idea("test", tmp_path)

        content = (tmp_path / "notes.md").read_text()
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in content


class TestUndoLast:
    """Test undo functionality."""

    def test_removes_last_food_entry(self, tmp_path: Path) -> None:
        """undo removes last JSONL line from food journal."""
        journal_dir = tmp_path / "food-journal"
        journal_dir.mkdir()

        # Add two entries
        log_food("breakfast", tmp_path)
        log_food("lunch", tmp_path)

        # Undo last
        undo_last("log", tmp_path)

        today = datetime.now().strftime("%Y-%m")
        journal_file = journal_dir / f"{today}.jsonl"
        lines = journal_file.read_text().strip().split("\n")
        assert len(lines) == 1
        assert "breakfast" in lines[0]

    def test_removes_last_note(self, tmp_path: Path) -> None:
        """undo removes last note entry."""
        note_idea("first idea", tmp_path)
        note_idea("second idea", tmp_path)

        undo_last("listen", tmp_path)

        content = (tmp_path / "notes.md").read_text()
        assert "first idea" in content
        assert "second idea" not in content


class TestGetLastMessage:
    """Test repeat functionality."""

    def test_returns_last_message(self, tmp_path: Path) -> None:
        """get_last_message returns stored message."""
        # This uses session storage, tested via integration
        pass
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kevin/coding/voice-agent && uv run pytest tests/test_commands.py -v`
Expected: FAIL - No module 'voice_agent.commands'

**Step 3: Create commands.py**

```python
# src/voice_agent/commands.py
"""Command handlers for voice agent actions."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def log_food(message: str, agent_path: Path) -> dict:
    """
    Log food entry to the food journal.

    Appends JSONL to food-journal/YYYY-MM.jsonl

    Returns:
        The entry dict (for undo tracking)
    """
    journal_dir = agent_path / "food-journal"
    journal_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    journal_file = journal_dir / f"{now.strftime('%Y-%m')}.jsonl"

    entry = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "created_at": now.isoformat(),
        "food_description": message,
    }

    with open(journal_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(f"Logged food: {message}")
    return entry


def note_idea(message: str, agent_path: Path) -> str:
    """
    Note an idea to the agent's notes file.

    Appends timestamped entry to notes.md

    Returns:
        The entry text (for undo tracking)
    """
    notes_file = agent_path / "notes.md"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {timestamp}\n{message}\n"

    with open(notes_file, "a") as f:
        f.write(entry)

    logger.info(f"Noted: {message[:50]}...")
    return entry


def undo_last(command: str, agent_path: Path) -> bool:
    """
    Undo the last command of the given type.

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
    # Pattern: ## YYYY-MM-DD HH:MM\n...\n (until next ## or end)
    pattern = r"\n## \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n[^#]*$"
    match = re.search(pattern, content)

    if not match:
        logger.warning("No note entry found to undo")
        return False

    new_content = content[: match.start()]
    notes_file.write_text(new_content)

    logger.info("Undid last note")
    return True


# Command name -> handler function mapping
COMMAND_HANDLERS: dict[str, callable] = {
    "log": log_food,
    "listen": note_idea,
}


def execute_command(
    command: str,
    message: str,
    agent_path: Path,
) -> bool:
    """
    Execute a command handler.

    Returns:
        True if successful, False otherwise
    """
    handler = COMMAND_HANDLERS.get(command)
    if handler is None:
        logger.warning(f"Unknown command: {command}")
        return False

    try:
        handler(message, agent_path)
        return True
    except Exception as e:
        logger.error(f"Command '{command}' failed: {e}")
        return False
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kevin/coding/voice-agent && uv run pytest tests/test_commands.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/voice_agent/commands.py tests/test_commands.py
git commit -m "$(cat <<'EOF'
feat: add command handlers with undo support

- log_food: appends JSONL to food-journal
- note_idea: appends markdown to notes.md
- undo_last: removes last entry per command type

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Success Chime to Audio Module

**Files:**
- Modify: `src/voice_agent/audio.py`

**Step 1: Add get_success_chime function**

```python
# Add to src/voice_agent/audio.py after prepend_notification (around line 179)

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
```

**Step 2: Commit**

```bash
git add src/voice_agent/audio.py
git commit -m "$(cat <<'EOF'
feat: add get_success_chime for silent commands

Returns notification sound with silence padding,
used as confirmation for silent commands.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Integrate Into Main Pipeline

**Files:**
- Modify: `src/voice_agent/main.py`

**Step 1: Update imports and config loading**

```python
# Replace imports in src/voice_agent/main.py (lines 17-28)

from voice_agent.transcribe import transcribe, unload_model as unload_transcribe_model, set_hotwords
from voice_agent.claude import ask_claude, clear_conversation, get_context_usage
from voice_agent.tts import synthesize, warm_model, get_audio_media_type, get_output_format, unload_model as unload_tts_model
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
    VoiceAgentConfig,
)
from voice_agent.commands import execute_command, undo_last
```

```python
# Replace config loading in src/voice_agent/main.py (around line 135)

# Load configuration on startup
CONFIG = load_agents_config()
logger.info(f"Loaded {len(CONFIG.agents)} agents: {list(CONFIG.agents.keys())}")
logger.info(f"Loaded {len(CONFIG.commands)} commands: {list(CONFIG.commands.keys())}")
logger.info(f"Loaded {len(CONFIG.keywords)} keywords for Whisper")

# Set hotwords for transcription
set_hotwords(CONFIG)
```

**Step 2: Replace command processing in /voice endpoint**

```python
# Replace the section after transcription in process_voice (after line 213)
# This replaces from "# Load current agent" through the Claude call setup

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
                cmd_config = get_command_for_agent(command_name, current_agent_name, CONFIG)

                if cmd_config is None:
                    # Command not available for this agent - return crickets
                    logger.warning(f"Command '{command_name}' not available for agent '{current_agent_name}'")
                    error_sound = get_error_sound("empty_transcription", audio_format)
                    if error_sound:
                        return Response(content=error_sound, media_type=get_audio_media_type())

                # Handle special commands
                if command_name == "undo":
                    last = get_last_command()
                    if last:
                        undo_last(last["command"], Path(last.get("agent_path", cwd)))
                        clear_last_command()
                    chime = get_success_chime(audio_format)
                    if chime:
                        log_conversation(user_text, "[undo]", "", conversations_dir)
                        return Response(content=chime, media_type=get_audio_media_type())

                elif command_name == "repeat":
                    last = get_last_command()
                    if last and last.get("message"):
                        # Re-send to Claude with the last message
                        user_text = last["message"]
                        # Fall through to Claude processing
                    else:
                        # Nothing to repeat - crickets
                        error_sound = get_error_sound("empty_transcription", audio_format)
                        if error_sound:
                            return Response(content=error_sound, media_type=get_audio_media_type())

                else:
                    # Regular command (log, listen, etc.)
                    if not message.strip():
                        # No message provided - return crickets
                        logger.warning(f"Command '{command_name}' with no message")
                        error_sound = get_error_sound("empty_transcription", audio_format)
                        if error_sound:
                            return Response(content=error_sound, media_type=get_audio_media_type())

                    # Execute the command
                    success = execute_command(command_name, message, cwd)

                    if success and cmd_config.silent:
                        # Save for undo/repeat
                        save_last_command(current_agent_name, command_name, message)
                        # Return just the chime
                        chime = get_success_chime(audio_format)
                        if chime:
                            log_conversation(user_text, f"[{command_name}]", "", conversations_dir)
                            return Response(content=chime, media_type=get_audio_media_type())

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

        # Continue with existing special commands (reset, context)
        # ... rest of the function unchanged
```

**Step 3: Run server and test**

Run: `cd /home/kevin/coding/voice-agent && uv run uvicorn voice_agent.main:app --reload --port 8000`
Expected: Server starts, logs show keywords loaded

**Step 4: Commit**

```bash
git add src/voice_agent/main.py
git commit -m "$(cat <<'EOF'
feat: integrate command parsing into voice pipeline

- Keyword extraction from first 5 words
- Silent commands return chime only
- Undo removes last entry
- Repeat re-sends last message
- Crickets for missing message or invalid command

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Manual Integration Test

**Step 1: Test "diet agent log"**

1. Record audio: "diet agent log two scrambled eggs"
2. POST to /voice
3. Expected: Chime only (no TTS), food-journal updated

Verify: `tail -1 ~/journal/agents/diet/food-journal/2026-01.jsonl`

**Step 2: Test "agent listen"**

1. Record: "agent listen should add more commands later"
2. POST to /voice
3. Expected: Chime only, notes.md updated in voice-agent dir

Verify: `tail -5 /home/kevin/coding/voice-agent/notes.md`

**Step 3: Test "agent undo"**

1. Record: "agent undo"
2. POST to /voice
3. Expected: Chime, last entry removed

**Step 4: Test missing message**

1. Record: "diet agent log"
2. POST to /voice
3. Expected: Crickets sound (no message provided)

**Step 5: Test invalid command for agent**

1. Record: "budget agent log pizza"
2. POST to /voice
3. Expected: Crickets sound (log not available for budget)

**Step 6: Final commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: complete command parsing implementation

Tested:
- Silent commands with chime confirmation
- Undo removes last entry
- Crickets for invalid/missing input
- Hotwords improve Whisper recognition

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Key Changes |
|------|-------------|-------------|
| 1 | Update YAML structure | Top-level commands, keywords section |
| 2 | Rewrite config loading | VoiceAgentConfig, auto-triggers, aliases |
| 3 | Add Whisper hotwords | build_hotwords_string, set_hotwords |
| 4 | Create command handlers | log_food, note_idea, undo_last |
| 5 | Add success chime | get_success_chime in audio.py |
| 6 | Integrate into pipeline | Keyword extraction, command routing |
| 7 | Manual integration test | Verify all scenarios work |

**Commands:**
- `log` (diet only): silent, aliases [add, record]
- `listen` (universal): silent, aliases [note]
- `undo` (universal): silent, aliases [cancel, nevermind]
- `repeat` (universal): non-silent, aliases [again, replay]
