"""Background research agent spawning."""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RESEARCH_TOOL_DIR = Path.home() / "journal" / "tools" / "research"


def spawn_research(query: str, output_dir: Path, topic_slug: str) -> Path:
    """
    Spawn detached Claude subprocess for background research.

    Args:
        query: The research query/topic
        output_dir: Directory to save research output (e.g., ~/journal/agents/career/research/)
        topic_slug: Kebab-case topic name for filename

    Returns:
        Path where research output will be written
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename with timestamp to prevent collisions
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    output_file = output_dir / f"{timestamp}-{topic_slug}.md"

    # Build prompt with output path instruction
    prompt = f"""Research the following topic thoroughly using web search:

{query}

Write your findings to: {output_file}

Requirements:
- Use WebSearch to find current, relevant information
- Include sources and links
- Structure with clear markdown sections
- Be comprehensive but focused
- Write directly to the file path above
"""

    # Launch detached subprocess
    cmd = [
        "claude", "-p",
        "--dangerously-skip-permissions",
        "--output-format", "text"
    ]

    logger.info(f"Spawning research subprocess for: {topic_slug}")
    logger.info(f"Output will be written to: {output_file}")

    # start_new_session=True detaches from parent process group
    # IMPORTANT: Must close stdin after writing so Claude sees EOF
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=RESEARCH_TOOL_DIR,
        start_new_session=True,
        text=True
    )
    proc.stdin.write(prompt)
    proc.stdin.close()

    return output_file
