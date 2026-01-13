"""Tests for command handlers."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from voice_agent.commands import (
    load_command_prompt,
    execute_command,
    undo_last,
    GLOBAL_COMMANDS_DIR,
)


class TestLoadCommandPrompt:
    """Test command prompt loading."""

    def test_loads_agent_specific_prompt(self, tmp_path: Path) -> None:
        """Agent-specific prompt takes precedence."""
        agent_path = tmp_path / "agent"
        cmd_dir = agent_path / "voice-commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "log.md").write_text("Agent-specific log prompt")

        result = load_command_prompt("log", agent_path)
        assert result == "Agent-specific log prompt"

    def test_falls_back_to_global_prompt(self, tmp_path: Path) -> None:
        """Falls back to global if no agent-specific prompt."""
        agent_path = tmp_path / "agent"
        agent_path.mkdir()

        # Global commands dir should have listen.md
        result = load_command_prompt("listen", agent_path)
        # If global exists, it should return content
        if (GLOBAL_COMMANDS_DIR / "listen.md").exists():
            assert result is not None
            assert "listen" in result.lower() or "note" in result.lower()

    def test_returns_none_for_missing_command(self, tmp_path: Path) -> None:
        """Returns None if command prompt doesn't exist."""
        agent_path = tmp_path / "agent"
        agent_path.mkdir()

        result = load_command_prompt("nonexistent", agent_path)
        assert result is None


class TestExecuteCommand:
    """Test command execution via Claude."""

    @patch("voice_agent.commands.subprocess.run")
    def test_calls_claude_with_prompt(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """execute_command calls Claude with the command prompt."""
        agent_path = tmp_path / "agent"
        cmd_dir = agent_path / "voice-commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "log.md").write_text("Log this food entry")

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = execute_command("log", "two eggs", agent_path)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "claude" in call_args[0][0]
        assert "--append-system-prompt" in call_args[0][0]
        assert call_args.kwargs["input"] == "two eggs"
        assert call_args.kwargs["cwd"] == agent_path

    @patch("voice_agent.commands.subprocess.run")
    def test_returns_false_on_claude_error(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Returns False if Claude fails."""
        agent_path = tmp_path / "agent"
        cmd_dir = agent_path / "voice-commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "log.md").write_text("Log prompt")

        mock_run.return_value = MagicMock(returncode=1, stderr="Error")

        result = execute_command("log", "test", agent_path)
        assert result is False

    def test_returns_false_for_missing_prompt(self, tmp_path: Path) -> None:
        """Returns False if no prompt found."""
        agent_path = tmp_path / "agent"
        agent_path.mkdir()

        result = execute_command("nonexistent", "test", agent_path)
        assert result is False


class TestUndoLast:
    """Test undo functionality."""

    def test_undo_removes_last_food_entry(self, tmp_path: Path) -> None:
        """undo_last removes last JSONL line from food journal."""
        journal_dir = tmp_path / "food-journal"
        journal_dir.mkdir()

        today = datetime.now().strftime("%Y-%m")
        journal_file = journal_dir / f"{today}.jsonl"
        journal_file.write_text('{"food":"breakfast"}\n{"food":"lunch"}\n')

        result = undo_last("log", tmp_path)

        assert result is True
        lines = journal_file.read_text().strip().split("\n")
        assert len(lines) == 1
        assert "breakfast" in lines[0]

    def test_undo_removes_last_note(self, tmp_path: Path) -> None:
        """undo_last removes last note entry."""
        notes_file = tmp_path / "notes.md"
        notes_file.write_text(
            "# Notes\n\n## 2024-01-01 10:00\nFirst idea\n\n## 2024-01-01 11:00\nSecond idea\n"
        )

        result = undo_last("listen", tmp_path)

        assert result is True
        content = notes_file.read_text()
        assert "First idea" in content
        assert "Second idea" not in content

    def test_undo_returns_false_for_unknown_command(self, tmp_path: Path) -> None:
        """undo_last returns False for unknown commands."""
        result = undo_last("unknown", tmp_path)
        assert result is False

    def test_undo_returns_false_for_empty_journal(self, tmp_path: Path) -> None:
        """undo_last returns False if journal is empty."""
        journal_dir = tmp_path / "food-journal"
        journal_dir.mkdir()

        today = datetime.now().strftime("%Y-%m")
        journal_file = journal_dir / f"{today}.jsonl"
        journal_file.write_text("")

        result = undo_last("log", tmp_path)
        assert result is False

    def test_undo_returns_false_for_missing_notes(self, tmp_path: Path) -> None:
        """undo_last returns False if notes.md doesn't exist."""
        result = undo_last("listen", tmp_path)
        assert result is False
