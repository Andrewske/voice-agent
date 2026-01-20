# Extended Features

## Files to Modify/Create
- `chat-ui/src/components/layout/Header.tsx` (modify)
- `chat-ui/src/components/layout/Sidebar.tsx` (new)
- `chat-ui/src/hooks/useAgents.ts` (new)
- `chat-ui/src/hooks/useConversations.ts` (new)
- `chat-ui/src/hooks/useTheme.ts` (new)
- `chat-ui/src/App.tsx` (modify)
- `chat-ui/src/index.css` (modify)

## Implementation Details

### 1. Agent Switcher (Header)
Using shadcn DropdownMenu:
- Shows current agent name in header
- Dropdown lists all available agents
- Active agent has checkmark
- Switching agent calls `/api/agents/switch` API
- Chat continues in same view (no clear) - agent colors distinguish context

```typescript
// useAgents hook
interface UseAgentsReturn {
  agents: Agent[]
  activeAgent: string | null
  switchAgent: (name: string) => Promise<void>
  isLoading: boolean
}
```

### 2. Conversation History Sidebar
Using shadcn Sheet (drawer):
- Hamburger menu button in header (left side)
- Slides in from left on mobile
- Lists conversations grouped by date
- Each item shows date + first message preview
- Clicking loads that conversation (read-only view)
- Current conversation highlighted

```typescript
// useConversations hook
interface UseConversationsReturn {
  conversations: ConversationSummary[]
  loadConversation: (date: string) => Promise<void>
  isLoading: boolean
}
```

Sidebar layout:
```
┌─────────────────────┐
│ Conversations    ✕  │
├─────────────────────┤
│ Today               │
│ ┌─────────────────┐ │
│ │ How's the proj..│ │
│ └─────────────────┘ │
│                     │
│ Yesterday           │
│ ┌─────────────────┐ │
│ │ Let's talk about│ │
│ └─────────────────┘ │
│ ...                 │
└─────────────────────┘
```

### 3. New Chat Button
- "+" button in header (right side)
- Calls `startNewSession()` from useChat
- Clears current messages
- Sets `new_session: true` for next API call
- Creates separate session file (hybrid model)

### 4. Dark Mode
Using Tailwind's class-based dark mode:

```typescript
// useTheme hook
function useTheme() {
  // Check system preference
  // Apply 'dark' class to documentElement
  // Listen for system preference changes
}
```

In `index.css`:
- Define CSS variables for light/dark themes
- shadcn/ui handles most via its theming

Color scheme:
- Light: white bg, slate text
- Dark: slate-900 bg, slate-100 text
- Accent: consistent across modes

### 5. Loading & Error States
- Skeleton loaders for conversation list
- Error toast/banner for API failures
- Retry mechanism for failed sends

## Acceptance Criteria
- [ ] Agent dropdown shows all agents from config
- [ ] Switching agent updates state without clearing chat
- [ ] New messages after switch show new agent's color/label
- [ ] Sidebar opens/closes smoothly on mobile
- [ ] Conversation history loads and displays correctly
- [ ] Clicking past conversation shows messages (read-only)
- [ ] New Chat button starts fresh session
- [ ] Dark mode follows system preference
- [ ] Error states show user-friendly messages

## Dependencies
- Task 03 (Core Chat UI) complete
- Task 01 (Backend) for API integration

## Testing
1. Switch agents, verify API call and UI update
2. Open sidebar, verify conversation list loads
3. Click past conversation, verify history displays
4. Toggle system dark mode, verify UI updates
5. Disconnect network, verify error handling
