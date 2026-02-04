import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Send, ChevronDown, Check, Paperclip, Loader2 } from 'lucide-react'

interface Agent {
  name: string
  active: boolean
}

interface ChatInputProps {
  onSend: (message: string) => void
  onSendAudio: (file: File) => void
  disabled?: boolean
  activeAgent: string | null
  agents: Agent[]
  onAgentSwitch: (agent: string) => void
}

type UploadState = 'idle' | 'uploading' | 'transcribing'

export function ChatInput({ onSend, onSendAudio, disabled, activeAgent, agents, onAgentSwitch }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    const allowedTypes = ['.m4a', '.mp3', '.wav', '.ogg', '.webm']
    const fileExt = file.name.toLowerCase().slice(file.name.lastIndexOf('.'))
    if (!allowedTypes.includes(fileExt)) {
      alert(`Invalid file type. Allowed: ${allowedTypes.join(', ')}`)
      e.target.value = '' // Reset input
      return
    }

    // Validate file size (25MB)
    const maxSize = 25 * 1024 * 1024
    if (file.size > maxSize) {
      alert('File too large. Maximum size is 25MB.')
      e.target.value = '' // Reset input
      return
    }

    // Send the audio file
    setUploadState('uploading')
    onSendAudio(file)
    e.target.value = '' // Reset input for next upload
  }

  const handleAttachmentClick = () => {
    fileInputRef.current?.click()
  }

  // Reset upload state when disabled changes (upload complete)
  useEffect(() => {
    if (!disabled && uploadState !== 'idle') {
      setUploadState('idle')
    }
  }, [disabled, uploadState])

  const isUploading = uploadState !== 'idle'
  const isDisabled = disabled || isUploading

  return (
    <div className="sticky bottom-0 p-4 pb-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex flex-col gap-3 rounded-2xl border border-zinc-700 bg-zinc-900 p-4 shadow-lg shadow-lime-500/5 focus-within:border-lime-500/50 focus-within:shadow-lime-500/10 transition-all">
          <input
            type="file"
            ref={fileInputRef}
            accept=".m4a,.mp3,.wav,.ogg,.webm"
            onChange={handleFileSelect}
            className="hidden"
          />
          <Textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message here..."
            disabled={isDisabled}
            className="min-h-[44px] max-h-32 resize-none border-0 bg-transparent text-white placeholder:text-zinc-500 focus-visible:ring-0 focus-visible:ring-offset-0 p-0"
            rows={1}
          />
          <div className="flex items-center justify-between gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 gap-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 px-3 rounded-lg border border-zinc-700"
                >
                  <span className="capitalize text-sm">{activeAgent || 'default'}</span>
                  <ChevronDown className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="bg-zinc-900 border-zinc-700">
                {agents.map((agent) => (
                  <DropdownMenuItem
                    key={agent.name}
                    onClick={() => onAgentSwitch(agent.name)}
                    className="gap-2 hover:bg-zinc-800 focus:bg-zinc-800"
                  >
                    {agent.active && <Check className="h-4 w-4 text-lime-500" />}
                    {!agent.active && <div className="w-4" />}
                    <span className="capitalize">{agent.name}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <div className="flex items-center gap-2">
              <Button
                onClick={handleAttachmentClick}
                disabled={isDisabled}
                size="icon"
                variant="ghost"
                className="h-10 w-10 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-40"
              >
                {isUploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Paperclip className="h-4 w-4" />
                )}
              </Button>
              <Button
                onClick={handleSend}
                disabled={isDisabled || !message.trim()}
                size="icon"
                className="h-10 w-10 rounded-xl bg-lime-500 text-black hover:bg-lime-400 disabled:opacity-40 disabled:bg-zinc-700 disabled:text-zinc-500"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
