"""Tests for transcription module."""

from pathlib import Path

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
