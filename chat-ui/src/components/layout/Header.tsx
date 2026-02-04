import { Button } from '@/components/ui/button'
import { Menu, Plus, PanelLeftClose } from 'lucide-react'

interface HeaderProps {
  onNewChat: () => void
  sidebarOpen: boolean
  onToggleSidebar: () => void
  activeAgent: string | null
}

const formatAgentName = (name: string | null): string => {
  if (!name || name === 'default') return 'Voice Agent'
  return name
    .split(/[-_]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function Header({
  onNewChat,
  sidebarOpen,
  onToggleSidebar,
  activeAgent,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleSidebar}
            className="text-zinc-400 hover:text-white hover:bg-zinc-800"
          >
            {sidebarOpen ? (
              <PanelLeftClose className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </Button>
          <span className="text-lg font-semibold text-white">{formatAgentName(activeAgent)}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewChat}
          className="text-zinc-400 hover:text-white hover:bg-zinc-800"
        >
          <Plus className="h-5 w-5" />
        </Button>
      </div>
    </header>
  )
}
