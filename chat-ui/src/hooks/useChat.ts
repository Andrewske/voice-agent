import { useState, useRef, useEffect } from 'react'
import { streamChat, type ChatEvent } from '@/api/client'
import type { MessageData } from '@/components/chat/MessageList'

export interface UseChatReturn {
  messages: MessageData[]
  isStreaming: boolean
  streamingText: string
  streamingThinking: string
  currentAgent: string
  sendMessage: (content: string) => Promise<void>
  startNewSession: () => void
}

export function useChat(currentAgent: string = 'default'): UseChatReturn {
  const [messages, setMessages] = useState<MessageData[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [streamingThinking, setStreamingThinking] = useState('')
  const abortControllerRef = useRef<AbortController | null>(null)

  // Cleanup: abort any in-flight stream on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
    }
  }, [])

  const sendMessage = async (content: string) => {
    // Add user message
    const userMessage: MessageData = {
      role: 'user',
      content,
      timestamp: new Date().toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
      }),
    }
    setMessages((prev) => [...prev, userMessage])

    // Start streaming
    setIsStreaming(true)
    setStreamingText('')
    setStreamingThinking('')

    // Track streaming content with ref to avoid stale closures
    let accumulatedText = ''
    let accumulatedThinking = ''

    const handleEvent = (event: ChatEvent) => {
      if (event.type === 'thinking') {
        accumulatedThinking += event.content
        setStreamingThinking(accumulatedThinking)
      } else if (event.type === 'text') {
        accumulatedText += event.content
        setStreamingText(accumulatedText)
      } else if (event.type === 'done') {
        // Finalize assistant message
        const assistantMessage: MessageData = {
          role: 'assistant',
          content: accumulatedText,
          thinking: accumulatedThinking || undefined,
          agent: currentAgent,
          timestamp: new Date().toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit',
          }),
        }
        setMessages((prev) => [...prev, assistantMessage])
        setIsStreaming(false)
        setStreamingText('')
        setStreamingThinking('')
      }
    }

    const handleError = (error: Error) => {
      console.error('Chat stream error:', error)
      setIsStreaming(false)
      // Add error message
      const errorMessage: MessageData = {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        agent: currentAgent,
      }
      setMessages((prev) => [...prev, errorMessage])
    }

    abortControllerRef.current = streamChat(content, handleEvent, handleError)
  }

  const startNewSession = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setMessages([])
    setIsStreaming(false)
    setStreamingText('')
    setStreamingThinking('')
  }

  return {
    messages,
    isStreaming,
    streamingText,
    streamingThinking,
    currentAgent,
    sendMessage,
    startNewSession,
  }
}
