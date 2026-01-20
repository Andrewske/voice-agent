import { useEffect, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Message } from './Message'
import { StreamingIndicator } from './StreamingIndicator'

export interface MessageData {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
  thinking?: string
  agent?: string
}

interface MessageListProps {
  messages: MessageData[]
  streamingContent?: { text: string; thinking: string; agent?: string }
  isStreaming: boolean
}

export function MessageList({ messages, streamingContent, isStreaming }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      const scrollContainer = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight
      }
    }
  }, [messages, streamingContent])

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-4">
      <div className="py-4 space-y-1">
        {messages.map((msg, idx) => (
          <Message
            key={idx}
            role={msg.role}
            content={msg.content}
            timestamp={msg.timestamp}
            thinking={msg.thinking}
            agent={msg.agent}
          />
        ))}
        {isStreaming && streamingContent && (
          <Message
            role="assistant"
            content={streamingContent.text || ''}
            thinking={streamingContent.thinking}
            agent={streamingContent.agent}
            isStreaming={true}
          />
        )}
        {isStreaming && !streamingContent?.text && !streamingContent?.thinking && (
          <StreamingIndicator />
        )}
      </div>
    </ScrollArea>
  )
}
