# Mem0 Memory Integration Design

**Date**: 2026-01-13
**Status**: Approved

## Problem

The voice agent lacks persistent memory across sessions. Each conversation starts fresh, requiring the user to re-establish context. We want the agent to remember facts, preferences, and ongoing topics across conversations.

## Goals

1. Persistent memory that survives session boundaries
2. Contextual awareness of recent conversation topics
3. Per-agent memory scoping (budget, career, etc.)
4. Graceful degradation when memory service is unavailable
5. Easy migration path from hosted to self-hosted

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Memory provider | Mem0 | Automatic fact extraction, deduplication, semantic search |
| Hosting | Mem0 hosted API (initially) | Fast to start, good UI for inspection, evaluating for job |
| Integration | Context injection (not MCP) | Simpler, guarantees context is always present |
| User scoping | Single `user_id="kevin"` | Metadata filtering for agents, allows cross-agent queries |
| Agent scoping | `metadata={"agent": "budget"}` | Clean separation without multiple user IDs |
| Saving strategy | Nightly batch per agent | Fewer API calls, more context for extraction |
| Context retrieval | Dual query (semantic + temporal) | Best coverage for both relevance and recency |

## Architecture

### Current Flow (No Memory)

```
Tasker → FastAPI → Whisper → Claude Code CLI → TTS → Audio Response
```

### New Flow (With Memory)

```
Tasker → FastAPI → Whisper
                      ↓
              ┌─────────────────┐
              │  Memory Module  │
              │                 │
              │  1. Parallel:   │
              │   - Semantic search (user message)
              │   - Temporal query (recent N)
              │  2. Dedupe & format
              │  3. Inject into system prompt
              └─────────────────┘
                      ↓
              Claude Code CLI → TTS → Audio Response
                      ↓
              (Response logged to conversations/)
                      ↓
              Nightly: Batch save to Mem0
```

## Implementation Details

### Memory Module

```python
from mem0 import MemoryClient
import asyncio

client = MemoryClient(api_key=os.environ["MEM0_API_KEY"])

async def get_memory_context(
    user_message: str,
    agent: str,
    user_id: str = "kevin",
    semantic_limit: int = 5,
    temporal_limit: int = 5
) -> str:
    """Fetch relevant memories via parallel semantic + temporal queries."""

    try:
        # Parallel queries
        semantic_task = asyncio.create_task(
            client.search(
                user_message,
                user_id=user_id,
                filters={"agent": agent},
                limit=semantic_limit
            )
        )
        temporal_task = asyncio.create_task(
            client.get_all(
                user_id=user_id,
                filters={"agent": agent},
                limit=temporal_limit
                # Sorted by recency by default
            )
        )

        semantic_results, temporal_results = await asyncio.gather(
            semantic_task, temporal_task
        )

        # Dedupe by memory ID
        seen_ids = set()
        memories = []

        for result in semantic_results.get("results", []):
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                memories.append(result["memory"])

        for result in temporal_results.get("results", []):
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                memories.append(result["memory"])

        if not memories:
            return ""

        return "## What I remember\n" + "\n".join(f"- {m}" for m in memories)

    except Exception as e:
        # Graceful degradation - log and continue without memory
        logger.warning(f"Memory fetch failed: {e}")
        return ""
```

### System Prompt Injection

```python
async def build_system_prompt(user_message: str, agent: str) -> str:
    memory_context = await get_memory_context(user_message, agent)

    base_prompt = read_file("voice-mode.md")

    if memory_context:
        return f"{base_prompt}\n\n{memory_context}"
    return base_prompt
```

### Nightly Batch Save

```python
#!/usr/bin/env python
"""Nightly script to batch-save daily conversations to Mem0."""

from mem0 import MemoryClient
from pathlib import Path
from datetime import date
import yaml

client = MemoryClient(api_key=os.environ["MEM0_API_KEY"])

def load_agent_config() -> dict:
    with open("voice-agent-config.yaml") as f:
        return yaml.safe_load(f)

def get_todays_conversation(agent_dir: Path) -> str | None:
    """Read today's conversation log if it exists."""
    today = date.today().isoformat()
    conv_file = agent_dir / "conversations" / f"{today}.md"

    if conv_file.exists():
        return conv_file.read_text()
    return None

def save_to_mem0(content: str, agent: str, user_id: str = "kevin"):
    """Save conversation to Mem0 with agent metadata."""
    client.add(
        content,
        user_id=user_id,
        metadata={
            "agent": agent,
            "type": "conversation",
            "date": date.today().isoformat()
        }
    )

def main():
    config = load_agent_config()

    # Process default agent
    default_conv = get_todays_conversation(Path("."))
    if default_conv:
        save_to_mem0(default_conv, agent="default")
        print("Saved default agent conversation")

    # Process specialized agents
    for agent_name, agent_config in config.get("agents", {}).items():
        agent_dir = Path(agent_config["directory"]).expanduser()
        conv = get_todays_conversation(agent_dir)

        if conv:
            save_to_mem0(conv, agent=agent_name)
            print(f"Saved {agent_name} agent conversation")

if __name__ == "__main__":
    main()
```

### Cron Setup

```bash
# Run nightly at 11:59 PM
59 23 * * * cd /home/kevin/coding/voice-agent && uv run python scripts/nightly-mem0-sync.py
```

## Metadata Schema

```python
{
    "agent": str,           # "default", "budget", "career", etc.
    "type": str,            # "conversation", "audio", "image" (future)
    "date": str,            # ISO date of original conversation
    "source": str           # "voice_agent", "claude_code" (future)
}
```

## Error Handling

1. **Mem0 API timeout**: 3-second timeout, continue without memory
2. **Mem0 API down**: Log warning, continue without memory context
3. **Invalid response**: Log error, continue without memory context
4. **Nightly sync failure**: Retry logic, alert if persistent failure

## Migration Path (Hosted → Self-Hosted)

When ready to migrate:

1. **Export all memories**:
   ```python
   data = client.get_all(user_id="kevin")
   ```

2. **Set up infrastructure**:
   - Qdrant: `docker run -p 6333:6333 qdrant/qdrant`
   - Ollama: Already running locally

3. **Configure self-hosted**:
   ```python
   config = {
       "llm": {"provider": "ollama", "config": {"model": "llama3.1:8b"}},
       "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text"}},
       "vector_store": {"provider": "qdrant", "config": {"host": "localhost", "port": 6333}}
   }
   ```

4. **Import memories**:
   ```python
   from mem0 import Memory
   m = Memory.from_config(config)
   for memory in data:
       m.add(memory["content"], user_id="kevin", metadata=memory["metadata"])
   ```

5. **Update imports**: `MemoryClient` → `Memory.from_config()`

6. **Adjust filter syntax**: `filters={"user_id": "x"}` → `user_id="x"`

## Future Considerations

1. **Claude Code integration**: Add hook to save coding sessions in agent directories
2. **Multi-modal memories**: Store voice clips, screenshots with `type` metadata
3. **Weekly synthesis**: Cron job to generate meta-summaries of patterns
4. **Cross-agent queries**: Allow default agent to search all agent memories

## Implementation Checklist

- [ ] Get Mem0 API key from mem0.ai
- [ ] Create `src/voice_agent/memory.py` module
- [ ] Integrate memory context into `claude.py`
- [ ] Verify sticky agent routing in `agents.py`
- [ ] Create `scripts/nightly-mem0-sync.py`
- [ ] Set up cron job for nightly sync
- [ ] Test with a few voice conversations
- [ ] Monitor memory quality in Mem0 dashboard
