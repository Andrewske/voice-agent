#!/usr/bin/env python
"""Nightly script to batch-save daily conversations to Mem0.

Run via cron at end of day:
    59 23 * * * cd /home/kevin/coding/voice-agent && uv run python scripts/nightly-mem0-sync.py
"""

import logging
import os
import sys
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root
PROJECT_DIR = Path(__file__).parent.parent

# Load .env and add src to path
load_dotenv(PROJECT_DIR / ".env")
sys.path.insert(0, str(PROJECT_DIR / "src"))

from voice_agent.memory import save_conversation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_FILE = PROJECT_DIR / "voice-agent-config.yaml"
DEFAULT_CONVERSATIONS_DIR = PROJECT_DIR / "conversations"


def load_agent_config() -> dict:
    """Load agent configuration from YAML."""
    if not CONFIG_FILE.exists():
        return {}

    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def get_todays_conversation(conversations_dir: Path) -> str | None:
    """Read today's conversation log if it exists and has content."""
    today = date.today().isoformat()
    conv_file = conversations_dir / f"{today}.md"

    if not conv_file.exists():
        return None

    content = conv_file.read_text().strip()
    if not content:
        return None

    return content


def sync_agent(agent_name: str, conversations_dir: Path) -> bool:
    """Sync a single agent's conversations to Mem0."""
    content = get_todays_conversation(conversations_dir)

    if not content:
        logger.info(f"No conversation today for agent: {agent_name}")
        return False

    success = save_conversation(
        content=content,
        agent=agent_name,
        date=date.today().isoformat(),
    )

    if success:
        logger.info(f"Synced {agent_name} conversation ({len(content)} chars)")
    else:
        logger.error(f"Failed to sync {agent_name} conversation")

    return success


def main() -> int:
    """Main entry point."""
    # Check for API key
    if not os.environ.get("MEM0_API_KEY"):
        logger.error("MEM0_API_KEY not set - cannot sync")
        return 1

    config = load_agent_config()
    synced = 0
    failed = 0

    # Sync default agent
    if sync_agent("default", DEFAULT_CONVERSATIONS_DIR):
        synced += 1

    # Sync specialized agents
    for agent_name, agent_config in config.get("agents", {}).items():
        agent_path = Path(agent_config["path"]).expanduser()
        conversations_dir = agent_path / "conversations"

        if not conversations_dir.exists():
            logger.debug(f"No conversations dir for agent: {agent_name}")
            continue

        if sync_agent(agent_name, conversations_dir):
            synced += 1
        else:
            # Only count as failed if there was content but save failed
            content = get_todays_conversation(conversations_dir)
            if content:
                failed += 1

    logger.info(f"Sync complete: {synced} agents synced, {failed} failed")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
