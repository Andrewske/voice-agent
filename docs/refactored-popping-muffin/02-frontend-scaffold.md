# Frontend Scaffold

## Files to Modify/Create
- `chat-ui/` (new directory)
- `chat-ui/package.json` (new)
- `chat-ui/vite.config.ts` (new)
- `chat-ui/tsconfig.json` (new)
- `chat-ui/tailwind.config.ts` (new)
- `chat-ui/src/index.css` (new)
- `chat-ui/src/main.tsx` (new)
- `chat-ui/src/App.tsx` (new)
- `chat-ui/src/lib/utils.ts` (new)
- `chat-ui/src/api/client.ts` (new)
- `chat-ui/components.json` (new - shadcn config)

## Implementation Details

### 1. Initialize Vite + React + TypeScript
```bash
cd /home/kevin/coding/voice-agent
npm create vite@latest chat-ui -- --template react-ts
cd chat-ui
npm install
```

### 2. Install and Configure Tailwind CSS
```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

Configure `tailwind.config.ts`:
- Content paths for src
- Dark mode: `class` (for system preference detection)
- Extend theme as needed

### 3. Install shadcn/ui
```bash
npx shadcn@latest init
```

Configuration:
- Style: Default
- Base color: Slate
- CSS variables: Yes

Install base components:
```bash
npx shadcn@latest add button input scroll-area dropdown-menu sheet collapsible
```

### 3.5. Install SSE Client Library
```bash
npm install @microsoft/fetch-event-source
```
This handles POST requests with SSE responses, proper event parsing, and reconnection.

### 4. Create API Client with SSE Support
In `src/api/client.ts`:

```typescript
import { fetchEventSource } from '@microsoft/fetch-event-source'

export interface ChatEvent {
  type: 'thinking' | 'text' | 'done'
  content: string
  conversationId?: string
}

export function streamChat(
  message: string,
  onEvent: (event: ChatEvent) => void,
  onError?: (error: Error) => void
): AbortController {
  const controller = new AbortController()

  fetchEventSource('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: controller.signal,
    onmessage(ev) {
      const event = JSON.parse(ev.data) as ChatEvent
      onEvent(event)
    },
    onerror(err) {
      onError?.(err)
    }
  })

  return controller // Call controller.abort() to cancel
}

export async function getConversations(): Promise<ConversationSummary[]> {
  const res = await fetch('/api/conversations')
  return res.json()
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`/api/conversations/${id}`)
  return res.json()
}

export async function getAgents(): Promise<Agent[]> {
  const res = await fetch('/api/agents')
  return res.json()
}

export async function switchAgent(agent: string): Promise<void> {
  await fetch('/api/agents/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent })
  })
}
```

### 4.5. Configure Vite Proxy for Development
In `vite.config.ts`, add proxy to avoid CORS issues during development:

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

### 5. Basic App Structure
`src/App.tsx`:
- Import global styles
- Set up basic layout shell
- Placeholder for chat interface

`src/main.tsx`:
- Standard React 18 createRoot setup
- Import index.css

## Acceptance Criteria
- [ ] `npm run dev` starts Vite dev server without errors
- [ ] Tailwind classes work (test with `bg-slate-900`)
- [ ] shadcn Button component renders correctly
- [ ] Dark mode classes apply based on system preference
- [ ] API client compiles without TypeScript errors
- [ ] `@microsoft/fetch-event-source` installed and imports work
- [ ] Vite proxy forwards `/api/*` requests to FastAPI on :8000

## Dependencies
- Task 01 (Backend) should be complete for integration testing
- Can develop UI in isolation with mock data initially

## Testing
```bash
cd chat-ui
npm run dev
# Open http://localhost:5173
# Verify Tailwind styles render
# Verify shadcn components import correctly
```
