# Core Chat UI

## Files to Modify/Create
- `chat-ui/src/components/chat/ChatInput.tsx` (new)
- `chat-ui/src/components/chat/Message.tsx` (new)
- `chat-ui/src/components/chat/MessageList.tsx` (new)
- `chat-ui/src/components/chat/ThinkingBlock.tsx` (new)
- `chat-ui/src/components/chat/StreamingIndicator.tsx` (new)
- `chat-ui/src/components/layout/Header.tsx` (new)
- `chat-ui/src/hooks/useChat.ts` (new)
- `chat-ui/src/App.tsx` (modify)

## Implementation Details

### 1. ChatInput Component
- Growing textarea (auto-resize based on content)
- Send button (right side, icon)
- Submit on Enter (Shift+Enter for newline)
- Disabled state while streaming
- Mobile-friendly: large touch target, bottom-sticky

```typescript
interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}
```

### 2. Message Component
- Two variants: user (right-aligned, accent bg) and assistant (left-aligned)
- Timestamp display
- Minimal markdown rendering (bold, italic only - no code blocks)
- `[chat]` marker hidden from display (internal only)
- **Agent indicator**: Show agent name label on assistant messages
- **Agent colors**: Each agent gets a distinct accent color (e.g., career=blue, diet=green, budget=amber)

```typescript
interface MessageProps {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  thinking?: string
  agent?: string // Agent name for color coding and label
}
```

### 3. ThinkingBlock Component
- Collapsible using shadcn Collapsible
- **During streaming**: Expanded, shows thinking content as it arrives
- **After completion**: Auto-collapses, shows "Thinking..." label with chevron
- Click to expand/collapse after completion
- Subtle styling (muted colors, smaller text, italic)

### 4. MessageList Component
- Scrollable container using shadcn ScrollArea
- Auto-scroll to bottom on new messages
- Date separators between different days
- Maintains scroll position when viewing history (scroll-to-bottom only for new messages)

```typescript
interface MessageListProps {
  messages: Message[]
  streamingContent?: { text: string; thinking: string }
}
```

### 5. StreamingIndicator Component
- Three-dot animation or pulsing cursor
- Shows while assistant is generating response
- Appears below last message

### 6. useChat Hook
Core state management:

```typescript
interface UseChatReturn {
  messages: Message[]
  isStreaming: boolean
  streamingText: string
  streamingThinking: string
  sendMessage: (content: string) => Promise<void>
  startNewSession: () => void
}
```

- Manages message history
- Handles SSE stream consumption
- Updates streaming state in real-time
- Appends completed message to history

### 7. Mobile-First Layout in App.tsx
```
┌─────────────────────────┐
│ Header (sticky)         │
├─────────────────────────┤
│                         │
│ MessageList (flex-1)    │
│ (scrollable)            │
│                         │
├─────────────────────────┤
│ ChatInput (sticky)      │
└─────────────────────────┘
```

- Full viewport height (`h-dvh` for mobile browsers)
- Header and input sticky, messages scroll between
- Safe area insets for notched phones

## Acceptance Criteria
- [ ] Can type message and send with Enter
- [ ] User messages appear right-aligned
- [ ] Assistant messages appear left-aligned with streaming
- [ ] Assistant messages show agent name label
- [ ] Different agents have distinct accent colors
- [ ] Thinking blocks expand during streaming, auto-collapse when done
- [ ] Thinking blocks can be manually expanded/collapsed after completion
- [ ] Auto-scroll works on new messages
- [ ] Streaming indicator shows during response
- [ ] Layout works on 412px width (Pixel 9)
- [ ] Touch targets are minimum 44px

## Dependencies
- Task 02 (Frontend Scaffold) complete
- Task 01 (Backend) for live integration

## Testing
1. Open dev server on mobile viewport (Chrome DevTools)
2. Send test message
3. Verify streaming response renders progressively
4. Verify thinking block expands/collapses
5. Verify scroll behavior on multiple messages
