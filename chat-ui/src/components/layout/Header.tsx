import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChevronDown, Plus, Check } from 'lucide-react'
import { Sidebar } from './Sidebar'

interface HeaderProps {
  activeAgent: string | null
  agents: Array<{ name: string; active: boolean }>
  onAgentSwitch: (agent: string) => void
  onNewChat: () => void
  onSelectConversation?: (conversationId: string) => void
}

export function Header({
  activeAgent,
  agents,
  onAgentSwitch,
  onNewChat,
  onSelectConversation,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-700 bg-slate-900 px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sidebar onSelectConversation={onSelectConversation} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-1">
                <span className="capitalize">{activeAgent || 'default'}</span>
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {agents.map((agent) => (
                <DropdownMenuItem
                  key={agent.name}
                  onClick={() => onAgentSwitch(agent.name)}
                  className="gap-2"
                >
                  {agent.active && <Check className="h-4 w-4" />}
                  {!agent.active && <div className="w-4" />}
                  <span className="capitalize">{agent.name}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <Button variant="ghost" size="icon" onClick={onNewChat}>
          <Plus className="h-5 w-5" />
        </Button>
      </div>
    </header>
  )
}
