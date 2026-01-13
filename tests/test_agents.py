"""Tests for agent routing and command parsing."""

import pytest

from voice_agent.agents import (
    load_agents_config,
    extract_keywords_from_window,
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


class TestExtractKeywordsFromWindow:
    """Test keyword extraction from user text."""

    @pytest.fixture
    def config(self) -> "VoiceAgentConfig":
        """Load the config for tests."""
        return load_agents_config()

    def test_basic_extraction(self, config) -> None:
        """Basic extraction of agent, command, and message."""
        result = extract_keywords_from_window("diet agent log two eggs", config)
        assert result["has_agent_keyword"] is True
        assert result["agent_name"] == "diet"
        assert result["command"] == "log"
        assert result["message"] == "two eggs"

    def test_no_agent_keyword(self, config) -> None:
        """Text without 'agent' keyword returns has_agent_keyword=False."""
        result = extract_keywords_from_window("what did I eat", config)
        assert result["has_agent_keyword"] is False
        assert result["agent_name"] is None
        assert result["command"] is None
        assert result["message"] == "what did I eat"

    def test_order_independence(self, config) -> None:
        """'agent diet' works same as 'diet agent'."""
        result1 = extract_keywords_from_window("diet agent log pizza", config)
        result2 = extract_keywords_from_window("agent diet log pizza", config)
        assert result1["agent_name"] == result2["agent_name"] == "diet"
        assert result1["command"] == result2["command"] == "log"
        assert result1["message"] == result2["message"] == "pizza"

    def test_default_agent(self, config) -> None:
        """Universal command with just 'agent' returns agent_name=None."""
        result = extract_keywords_from_window("agent listen idea", config)
        assert result["has_agent_keyword"] is True
        assert result["agent_name"] is None
        assert result["command"] == "listen"
        assert result["message"] == "idea"

    def test_aliases_work(self, config) -> None:
        """Command alias 'add' maps to canonical command 'log'."""
        result = extract_keywords_from_window("diet agent add pizza", config)
        assert result["has_agent_keyword"] is True
        assert result["agent_name"] == "diet"
        assert result["command"] == "log"  # canonical name, not alias

    def test_multi_word_agent(self, config) -> None:
        """Multi-word agent 'video games' is matched."""
        result = extract_keywords_from_window("video games agent listen", config)
        assert result["has_agent_keyword"] is True
        assert result["agent_name"] == "video-games"  # canonical hyphenated name
