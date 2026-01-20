import { ThinkingBlock } from './ThinkingBlock'

interface MessageProps {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
  thinking?: string
  agent?: string
  isStreaming?: boolean
}

// Agent color mapping
const agentColors: Record<string, string> = {
  default: 'bg-blue-600',
  career: 'bg-blue-600',
  diet: 'bg-green-600',
  budget: 'bg-amber-600',
  coding: 'bg-purple-600',
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
  const agentColor = agentColors[agent] || agentColors.default

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[85%] ${isUser ? 'order-1' : 'order-2'}`}>
        {!isUser && agent && (
          <div className="flex items-center gap-2 mb-1 ml-3">
            <div className={`h-2 w-2 rounded-full ${agentColor}`} />
            <span className="text-xs text-slate-400 capitalize">{agent}</span>
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-2 ${
            isUser
              ? 'bg-blue-600 text-white'
              : 'bg-slate-800 text-slate-100 border border-slate-700'
          }`}
        >
          <div className="whitespace-pre-wrap break-words">{content}</div>
          {timestamp && (
            <div className={`text-xs mt-1 ${isUser ? 'text-blue-200' : 'text-slate-500'}`}>
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
