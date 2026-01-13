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
SESSION_FILE = PROJECT_DIR / ".agent-session.json"


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


def save_last_command(agent_name: str | None, command: str, message: str, agent_path: Path) -> None:
    """Save last command for undo/repeat functionality."""
    data = _load_session_data()
    data["last_command"] = {
        "agent": agent_name,
        "command": command,
        "message": message,
        "agent_path": str(agent_path),
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
