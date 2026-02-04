import { useState, useEffect } from 'react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ChevronDown } from 'lucide-react'

interface ThinkingBlockProps {
  content: string
  isStreaming?: boolean
}

export function ThinkingBlock({ content, isStreaming = false }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(isStreaming)

  // Auto-expand during streaming, auto-collapse when done
  useEffect(() => {
    setIsOpen(isStreaming)
  }, [isStreaming])

  if (!content && !isStreaming) return null

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="mt-2">
      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
        <ChevronDown
          className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-0' : '-rotate-90'}`}
        />
        <span className="italic">Thinking...</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1 text-sm text-zinc-500 italic pl-4 border-l-2 border-zinc-700">
        {content}
      </CollapsibleContent>
    </Collapsible>
  )
}
