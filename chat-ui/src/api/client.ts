import { fetchEventSource } from '@microsoft/fetch-event-source'

export interface ChatEvent {
  type: 'transcription' | 'thinking' | 'text' | 'done' | 'error'
  content: string
  conversationId?: string
}

export interface ConversationSummary {
  id: string
  date: string
  preview: string
  agent?: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
}

export interface Conversation {
  id: string
  messages: Message[]
}

export interface Agent {
  name: string
  active: boolean
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
      try {
        const data = JSON.parse(ev.data)
        onEvent({
          type: ev.event as ChatEvent['type'],
          content: data.content || '',
          conversationId: data.conversation_id,
        })
      } catch (error) {
        console.error('Failed to parse SSE message:', error)
      }
    },
    onerror(err) {
      onError?.(err instanceof Error ? err : new Error(String(err)))
      throw err // Stop reconnection attempts
    },
    openWhenHidden: true,
  })

  return controller
}

export function streamChatAudio(
  file: File,
  onEvent: (event: ChatEvent) => void,
  onError?: (error: Error) => void
): AbortController {
  const controller = new AbortController()

  const formData = new FormData()
  formData.append('file', file)

  fetchEventSource('/api/chat/audio', {
    method: 'POST',
    body: formData,
    signal: controller.signal,
    onmessage(ev) {
      try {
        const data = JSON.parse(ev.data)
        onEvent({
          type: ev.event as ChatEvent['type'],
          content: data.content || '',
          conversationId: data.conversation_id,
        })
      } catch (error) {
        console.error('Failed to parse SSE message:', error)
      }
    },
    onerror(err) {
      onError?.(err instanceof Error ? err : new Error(String(err)))
      throw err // Stop reconnection attempts
    },
    openWhenHidden: true,
  })

  return controller
}

export async function getConversations(): Promise<ConversationSummary[]> {
  const res = await fetch('/api/conversations')
  if (!res.ok) throw new Error('Failed to fetch conversations')
  return res.json()
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`/api/conversations/${id}`)
  if (!res.ok) throw new Error('Failed to fetch conversation')
  return res.json()
}

export interface RecentMessage {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  timestamp?: string
}

export async function getRecentMessages(days: number = 3): Promise<RecentMessage[]> {
  const res = await fetch(`/api/conversations/recent?days=${days}`)
  if (!res.ok) throw new Error('Failed to fetch recent messages')
  const data = await res.json()
  return data.messages
}

export async function getAgents(): Promise<Agent[]> {
  const res = await fetch('/api/agents')
  if (!res.ok) throw new Error('Failed to fetch agents')
  return res.json()
}

export async function switchAgent(agent: string): Promise<void> {
  const res = await fetch('/api/agents/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent }),
  })
  if (!res.ok) throw new Error('Failed to switch agent')
}
