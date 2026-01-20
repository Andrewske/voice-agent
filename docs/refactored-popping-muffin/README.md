# Chat Agent Implementation

## Overview

Add a chat interface to the voice-agent project, enabling text-based conversations that share context with voice conversations. The chat UI will be accessible via `https://chat.piserver:8443` when connected to Tailscale.

**Key Features:**
- React + Vite + Tailwind + shadcn/ui frontend
- SSE streaming for real-time responses (using `@microsoft/fetch-event-source`)
- Shared conversation model (voice and chat share same Claude session)
- Mobile-first responsive design (optimized for Pixel 9)
- Dark mode with system preference detection
- Agent switching with color-coded messages
- Conversation history (reads Claude's native JSONL)

## Task Sequence

1. [01-backend-chat-endpoint.md](./01-backend-chat-endpoint.md) - Add `/api/chat` SSE endpoint, `/api/conversations` and `/api/agents` REST endpoints, async streaming in claude.py
2. [02-frontend-scaffold.md](./02-frontend-scaffold.md) - Initialize Vite + React + TypeScript, configure Tailwind and shadcn/ui, create API client with SSE support
3. [03-core-chat-ui.md](./03-core-chat-ui.md) - Build ChatInput, Message (with agent colors), MessageList, ThinkingBlock components and useChat hook
4. [04-extended-features.md](./04-extended-features.md) - Add agent switcher, conversation history sidebar, new chat button, dark mode
5. [05-deployment.md](./05-deployment.md) - Docker Compose on Pi, Caddy reverse proxy, `chat.piserver:8443`

## Success Criteria

- [ ] Chat UI accessible at `https://chat.piserver:8443` (Tailscale only)
- [ ] Messages stream in real-time with thinking blocks
- [ ] Thinking blocks expand during streaming, auto-collapse when done
- [ ] Voice and chat share conversation context (same Claude session)
- [ ] Agent switching works with color-coded messages
- [ ] Conversation history viewable in sidebar (reads Claude's JSONL)
- [ ] UI works well on Pixel 9 (mobile-first)
- [ ] Dark mode follows system preference
- [ ] HTTPS via Caddy internal TLS

## Execution Instructions

1. Execute tasks in numerical order (01 → 05)
2. Each task file contains:
   - Files to modify/create
   - Implementation details
   - Acceptance criteria
   - Dependencies
3. Verify acceptance criteria before moving to next task

## Architecture

```
Tailscale Network
       │
       ▼
┌─────────────────────────────────────────────────┐
│              Raspberry Pi                        │
│                                                  │
│  Caddy (:8443) ──► Docker: FastAPI (:8001)      │
│                    ├── /voice (existing)         │
│                    ├── /api/chat (SSE)           │
│                    ├── /api/conversations        │
│                    ├── /api/agents               │
│                    └── /* (React SPA)            │
│                          │                       │
│            Shared: claude.py, memory.py,         │
│                    ~/.claude/conversations/      │
└─────────────────────────────────────────────────┘
```

## Dependencies

- Existing voice-agent FastAPI server
- Docker and Docker Compose on Pi
- Caddy installed and running on Pi
- Node.js/npm for frontend build (local dev machine)
- uv for Python dependency management

## Key Files

**Backend (modify):**
- `src/voice_agent/main.py`
- `src/voice_agent/claude.py`

**Frontend (new):**
- `chat-ui/` - entire new directory
- Key components: `ChatInput`, `Message`, `MessageList`, `ThinkingBlock`, `Header`, `Sidebar`
- Hooks: `useChat`, `useAgents`, `useConversations`, `useTheme`

**Config:**
- Caddyfile (add `chat.piserver:8443` block)
- docker-compose.yml and Dockerfile on Pi
