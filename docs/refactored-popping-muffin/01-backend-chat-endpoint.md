# Backend Chat Endpoint

## Files to Modify/Create
- `src/voice_agent/main.py` (modify)
- `src/voice_agent/claude.py` (modify)

## Implementation Details

### 1. Add Async Streaming Function for Chat
In `claude.py`, add a new async generator function `stream_claude()`:
- Use `asyncio.create_subprocess_exec()` to run Claude CLI
- Iterate stdout lines asynchronously as they arrive
- Yield parsed chunks (thinking, text) as they stream
- Keep existing `ask_claude()` unchanged for voice endpoint (blocking is fine there)

```python
async def stream_claude(
    prompt: str,
    cwd: Path | None = None,
    conversations_dir: Path | None = None,
    agent: str = "default",
) -> AsyncGenerator[tuple[str, str, str], None]:
    """
    Stream Claude response as async generator.
    Yields: (event_type, content, conversation_id) tuples
    event_type: 'thinking' | 'text' | 'done'
    """
    # Build CLI args same as ask_claude
    # Use asyncio.create_subprocess_exec with stdout=PIPE
    # Read lines, parse JSONL, yield chunks
```

### 2. Add `/api/chat` SSE Endpoint
In `main.py`, create new endpoint:
```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    # ChatRequest: { message: str }
    # Return EventSourceResponse with SSE stream
    # Use stream_claude() async generator
    # Event types: thinking, text, done
```

### 3. Add `/api/conversations` Endpoints
```python
@app.get("/api/conversations")
# Returns: [{ id: str, date: str, preview: str }, ...]
# List conversation IDs from session files, map to dates

@app.get("/api/conversations/{conversation_id}")
# Returns: { id: str, messages: [...] }
# Read directly from Claude Code's conversation JSONL at:
# ~/.claude/projects/{project-hash}/conversations/{conversation_id}.jsonl
# Parse JSONL, extract user/assistant messages
```

### 4. Add `/api/agents` Endpoints
```python
@app.get("/api/agents")
# Returns: [{ name: str, active: bool }, ...]
# Read from voice-agent-config.yaml, check .agent-session.json for active

@app.post("/api/agents/switch")
# Request: { agent: str }
# Update .agent-session.json, return new conversation state
```

### 5. Update Conversation Logging
Modify `log_conversation()` to accept optional `source` parameter:
- Default: no marker (voice)
- `source="chat"`: adds `[chat]` marker to timestamp header

### 6. Session Management
Voice and chat share the same Claude conversation session:
- Both read/write to the same `.claude-session.json`
- Single conversation thread with shared context
- No separate session files needed

## Acceptance Criteria
- [ ] `POST /api/chat` returns SSE stream with thinking and text events
- [ ] SSE events stream progressively as Claude generates (not buffered)
- [ ] `GET /api/conversations` lists conversation IDs with dates
- [ ] `GET /api/conversations/{id}` reads Claude's native JSONL and returns structured messages
- [ ] `GET /api/agents` returns agent list with active status
- [ ] `POST /api/agents/switch` updates active agent
- [ ] Chat messages logged with `[chat]` marker in markdown
- [ ] Existing `/voice` endpoint unchanged

## Dependencies
None - this is the foundational backend work.

## Testing
```bash
# Test SSE streaming
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'

# Test conversations list
curl http://localhost:8000/api/conversations

# Test agents
curl http://localhost:8000/api/agents
```
