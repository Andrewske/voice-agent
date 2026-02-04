import { useState } from 'react'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { MessageList, type MessageData } from '@/components/chat/MessageList'
import { ChatInput } from '@/components/chat/ChatInput'
import { useChat } from '@/hooks/useChat'
import { useAgents } from '@/hooks/useAgents'
import { useTheme } from '@/hooks/useTheme'
import { useConversations } from '@/hooks/useConversations'

function App() {
  useTheme() // Initialize dark mode

  const { agents, activeAgent, switchAgent } = useAgents()
  const [historicalMessages, setHistoricalMessages] = useState<MessageData[] | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { loadConversation, refresh: refreshConversations } = useConversations()

  const {
    messages,
    isStreaming,
    streamingText,
    streamingThinking,
    currentAgent,
    sendMessage,
    sendAudioMessage,
    startNewSession,
    loadMessages,
  } = useChat(activeAgent || 'default')

  // Use historical messages if viewing history, otherwise active chat
  const displayMessages = historicalMessages ?? messages
  const isViewingHistory = historicalMessages !== null

  const streamingContent =
    isStreaming && (streamingText || streamingThinking)
      ? { text: streamingText, thinking: streamingThinking, agent: currentAgent }
      : undefined

  const handleAgentSwitch = async (agentName: string) => {
    try {
      setHistoricalMessages(null) // Clear historical view when switching agents
      await switchAgent(agentName)
      await refreshConversations()
    } catch (error) {
      console.error('Failed to switch agent:', error)
    }
  }

  const handleNewChat = () => {
    startNewSession()
    setHistoricalMessages(null)
  }

  const handleSelectConversation = async (conversationId: string, date: string) => {
    const conversation = await loadConversation(conversationId)
    if (conversation) {
      // Convert conversation messages to MessageData format
      const converted: MessageData[] = conversation.messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
        thinking: msg.thinking,
      }))

      // Check if this is today's conversation
      const today = new Date()
      const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

      if (date === todayStr) {
        // Today's conversation - load into active chat so user can continue
        loadMessages(converted)
        setHistoricalMessages(null)
      } else {
        // Historical conversation - view only
        setHistoricalMessages(converted)
      }
    }
  }

  return (
    <div className="h-dvh flex bg-background text-foreground">
      <Sidebar
        isOpen={sidebarOpen}
        onSelectConversation={handleSelectConversation}
        activeAgent={activeAgent}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <Header
          onNewChat={handleNewChat}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          activeAgent={activeAgent}
        />
        <MessageList
          messages={displayMessages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
        <ChatInput
          onSend={sendMessage}
          onSendAudio={sendAudioMessage}
          disabled={isStreaming || isViewingHistory}
          activeAgent={activeAgent}
          agents={agents}
          onAgentSwitch={handleAgentSwitch}
        />
      </div>
    </div>
  )
}

export default App
