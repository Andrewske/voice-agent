import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Menu } from 'lucide-react'
import { useConversations } from '@/hooks/useConversations'

interface SidebarProps {
  onSelectConversation?: (conversationId: string) => void
}

export function Sidebar({ onSelectConversation }: SidebarProps) {
  const { conversations, isLoading } = useConversations()

  // Group conversations by date
  const groupedConversations = conversations.reduce(
    (acc, conv) => {
      const date = new Date(conv.date)
      const today = new Date()
      const yesterday = new Date(today)
      yesterday.setDate(yesterday.getDate() - 1)

      let label = conv.date
      if (date.toDateString() === today.toDateString()) {
        label = 'Today'
      } else if (date.toDateString() === yesterday.toDateString()) {
        label = 'Yesterday'
      } else {
        label = date.toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
        })
      }

      if (!acc[label]) {
        acc[label] = []
      }
      acc[label].push(conv)
      return acc
    },
    {} as Record<string, typeof conversations>
  )

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-80">
        <SheetHeader>
          <SheetTitle>Conversations</SheetTitle>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-8rem)] mt-4">
          {isLoading ? (
            <div className="text-sm text-slate-500">Loading...</div>
          ) : conversations.length === 0 ? (
            <div className="text-sm text-slate-500">No conversations yet</div>
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedConversations).map(([label, convs]) => (
                <div key={label}>
                  <h3 className="text-xs font-semibold text-slate-500 uppercase mb-2">
                    {label}
                  </h3>
                  <div className="space-y-1">
                    {convs.map((conv) => (
                      <button
                        key={conv.id}
                        onClick={() => onSelectConversation?.(conv.id)}
                        className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors"
                      >
                        <div className="text-sm text-slate-200 line-clamp-2">
                          {conv.preview || 'Empty conversation'}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
