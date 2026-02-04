import { ThinkingBlock } from './ThinkingBlock'

interface MessageProps {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
  thinking?: string
  agent?: string
  isStreaming?: boolean
}

export function Message({
  role,
  content,
  timestamp,
  thinking,
  agent = 'default',
  isStreaming = false,
}: MessageProps) {
  const isUser = role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[85%] ${isUser ? 'order-1' : 'order-2'}`}>
        {!isUser && agent && (
          <div className="flex items-center gap-2 mb-1 ml-3">
            <span className="text-xs text-zinc-500 capitalize">{agent}</span>
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-lime-500 text-black'
              : 'bg-zinc-900 text-zinc-100 border border-zinc-800'
          }`}
        >
          <div className="whitespace-pre-wrap break-words">{content}</div>
          {timestamp && (
            <div className={`text-xs mt-1.5 ${isUser ? 'text-black/60' : 'text-zinc-500'}`}>
              {timestamp}
            </div>
          )}
        </div>
        {!isUser && (thinking || isStreaming) && (
          <div className="ml-3">
            <ThinkingBlock content={thinking || ''} isStreaming={isStreaming} />
          </div>
        )}
      </div>
    </div>
  )
}
