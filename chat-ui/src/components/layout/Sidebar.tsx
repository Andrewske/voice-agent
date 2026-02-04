import { useState } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Search } from 'lucide-react'
import { useConversations } from '@/hooks/useConversations'

interface SidebarProps {
  isOpen: boolean
  onSelectConversation?: (conversationId: string, date: string) => void
  activeAgent?: string | null
}

export function Sidebar({ isOpen, onSelectConversation, activeAgent }: SidebarProps) {
  const { conversations, isLoading } = useConversations()
  const [searchQuery, setSearchQuery] = useState('')

  const getLocalDateString = (d: Date): string => {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }

  const todayStr = getLocalDateString(new Date())
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = getLocalDateString(yesterday)

  const filteredConversations = conversations.filter((conv) => {
    const matchesSearch = conv.preview?.toLowerCase().includes(searchQuery.toLowerCase())
    // Map "default" to "voice-agent" since backend stores default conversations there
    const agentToMatch = activeAgent === 'default' ? 'voice-agent' : activeAgent
    const matchesAgent = !agentToMatch || conv.agent === agentToMatch
    return matchesSearch && matchesAgent
  })

  const groupedConversations = filteredConversations.reduce(
    (acc, conv) => {
      let label = conv.date
      if (conv.date === todayStr) {
        label = 'Today'
      } else if (conv.date === yesterdayStr) {
        label = 'Yesterday'
      } else {
        const date = new Date(conv.date + 'T12:00:00')
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
    <aside
      className={`
        h-full border-r border-zinc-800 bg-zinc-950 flex-shrink-0
        transition-all duration-300 ease-in-out overflow-hidden
        ${isOpen ? 'w-80' : 'w-0'}
      `}
    >
      <div className="flex flex-col h-full w-80">
        <div className="p-4 pb-2">
          <h2 className="text-lg font-semibold text-white">Conversations</h2>
        </div>

        <div className="px-4 pb-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-lime-500 focus:border-lime-500"
            />
          </div>
        </div>

        <ScrollArea className="flex-1 px-4">
          {isLoading ? (
            <div className="text-sm text-zinc-500 py-4">Loading...</div>
          ) : filteredConversations.length === 0 ? (
            <div className="text-sm text-zinc-500 py-4">
              {searchQuery ? 'No matching conversations' : 'No conversations yet'}
            </div>
          ) : (
            <div className="space-y-4 pb-4">
              {Object.entries(groupedConversations).map(([label, convs]) => (
                <div key={label}>
                  <h3 className="text-xs font-medium text-lime-500 mb-2">
                    {label}
                  </h3>
                  <div className="space-y-1">
                    {convs.map((conv) => (
                      <button
                        key={conv.id}
                        onClick={() => onSelectConversation?.(conv.id, conv.date)}
                        className="w-full text-left px-3 py-2 rounded-lg hover:bg-zinc-800 transition-colors group"
                      >
                        <div className="text-sm text-zinc-300 group-hover:text-white line-clamp-2">
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
      </div>
    </aside>
  )
}
