import { useState, useRef, useEffect } from 'react'
import { streamChat, streamChatAudio, getRecentMessages, type ChatEvent } from '@/api/client'
import type { MessageData } from '@/components/chat/MessageList'

export interface UseChatReturn {
  messages: MessageData[]
  isStreaming: boolean
  streamingText: string
  streamingThinking: string
  currentAgent: string
  isLoadingHistory: boolean
  sendMessage: (content: string) => Promise<void>
  sendAudioMessage: (file: File) => Promise<void>
  startNewSession: () => void
  loadMessages: (messages: MessageData[]) => void
}

export function useChat(currentAgent: string = 'default'): UseChatReturn {
  const [messages, setMessages] = useState<MessageData[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)
  const [streamingText, setStreamingText] = useState('')
  const [streamingThinking, setStreamingThinking] = useState('')
  const abortControllerRef = useRef<AbortController | null>(null)

  // Load recent messages on mount and when agent changes
  useEffect(() => {
    const loadHistory = async () => {
      try {
        setIsLoadingHistory(true)
        setMessages([]) // Clear immediately to avoid showing stale messages
        const recentMessages = await getRecentMessages(3)
        const converted: MessageData[] = recentMessages.map((msg) => ({
          role: msg.role,
          content: msg.content,
          thinking: msg.thinking,
          timestamp: msg.timestamp,
        }))
        setMessages(converted)
      } catch (error) {
        console.error('Failed to load recent messages:', error)
      } finally {
        setIsLoadingHistory(false)
      }
    }
    loadHistory()
  }, [currentAgent])

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
      if (event.type === 'transcription') {
        // Update the placeholder user message with actual transcription
        setMessages((prev) => {
          const updated = [...prev]
          // Find and update the last user message (the placeholder)
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === 'user') {
              updated[i] = { ...updated[i], content: event.content }
              break
            }
          }
          return updated
        })
      } else if (event.type === 'thinking') {
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
      } else if (event.type === 'error') {
        // Handle error events
        setIsStreaming(false)
        const errorMessage: MessageData = {
          role: 'assistant',
          content: event.content || 'Sorry, something went wrong. Please try again.',
          agent: currentAgent,
        }
        setMessages((prev) => [...prev, errorMessage])
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

  const sendAudioMessage = async (file: File) => {
    // Add placeholder user message immediately
    const placeholderMessage: MessageData = {
      role: 'user',
      content: '🎤 Audio message',
      timestamp: new Date().toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
      }),
    }
    setMessages((prev) => [...prev, placeholderMessage])

    // Start streaming
    setIsStreaming(true)
    setStreamingText('')
    setStreamingThinking('')

    // Track streaming content with ref to avoid stale closures
    let accumulatedText = ''
    let accumulatedThinking = ''

    const handleEvent = (event: ChatEvent) => {
      if (event.type === 'transcription') {
        // Update the placeholder user message with actual transcription
        setMessages((prev) => {
          const updated = [...prev]
          // Find and update the last user message (the placeholder)
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === 'user') {
              updated[i] = { ...updated[i], content: event.content }
              break
            }
          }
          return updated
        })
      } else if (event.type === 'thinking') {
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
      } else if (event.type === 'error') {
        // Handle error events
        setIsStreaming(false)
        const errorMessage: MessageData = {
          role: 'assistant',
          content: event.content || 'Sorry, something went wrong. Please try again.',
          agent: currentAgent,
        }
        setMessages((prev) => [...prev, errorMessage])
      }
    }

    const handleError = (error: Error) => {
      console.error('Audio chat stream error:', error)
      setIsStreaming(false)
      // Add error message
      const errorMessage: MessageData = {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        agent: currentAgent,
      }
      setMessages((prev) => [...prev, errorMessage])
    }

    abortControllerRef.current = streamChatAudio(file, handleEvent, handleError)
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

  const loadMessages = (newMessages: MessageData[]) => {
    setMessages(newMessages)
  }

  return {
    messages,
    isStreaming,
    streamingText,
    streamingThinking,
    currentAgent,
    isLoadingHistory,
    sendMessage,
    sendAudioMessage,
    startNewSession,
    loadMessages,
  }
}
