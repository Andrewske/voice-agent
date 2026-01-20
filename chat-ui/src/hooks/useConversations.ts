import { useState, useEffect } from 'react'
import {
  getConversations,
  getConversation,
  type ConversationSummary,
  type Conversation,
} from '@/api/client'

export interface UseConversationsReturn {
  conversations: ConversationSummary[]
  loadConversation: (id: string) => Promise<Conversation | null>
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useConversations(): UseConversationsReturn {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadConversations()
  }, [])

  const loadConversations = async () => {
    try {
      setIsLoading(true)
      const data = await getConversations()
      setConversations(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations')
    } finally {
      setIsLoading(false)
    }
  }

  const loadConversation = async (id: string): Promise<Conversation | null> => {
    try {
      const conversation = await getConversation(id)
      return conversation
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversation')
      return null
    }
  }

  return {
    conversations,
    loadConversation,
    isLoading,
    error,
    refresh: loadConversations,
  }
}
