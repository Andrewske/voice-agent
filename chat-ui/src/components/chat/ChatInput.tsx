import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Send } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${textarea.scrollHeight}px`
    }
  }, [message])

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message.trim())
      setMessage('')
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="sticky bottom-0 border-t border-slate-700 bg-slate-900 p-4">
      <div className="flex gap-2 items-end">
        <Textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          disabled={disabled}
          className="min-h-[44px] max-h-32 resize-none bg-slate-800 border-slate-700 text-slate-100 placeholder:text-slate-500"
          rows={1}
        />
        <Button
          onClick={handleSend}
          disabled={disabled || !message.trim()}
          size="icon"
          className="h-11 w-11 flex-shrink-0"
        >
          <Send className="h-5 w-5" />
        </Button>
      </div>
    </div>
  )
}
