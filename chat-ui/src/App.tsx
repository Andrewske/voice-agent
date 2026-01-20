import { useState } from 'react'
import { Header } from '@/components/layout/Header'
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
  const { loadConversation } = useConversations()

  const {
    messages,
    isStreaming,
    streamingText,
    streamingThinking,
    currentAgent,
    sendMessage,
    startNewSession,
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
      await switchAgent(agentName)
    } catch (error) {
      console.error('Failed to switch agent:', error)
    }
  }

  const handleNewChat = () => {
    startNewSession()
    setHistoricalMessages(null)
  }

  const handleSelectConversation = async (conversationId: string) => {
    const conversation = await loadConversation(conversationId)
    if (conversation) {
      // Convert conversation messages to MessageData format
      const converted: MessageData[] = conversation.messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
        thinking: msg.thinking,
      }))
      setHistoricalMessages(converted)
    }
  }

  return (
    <div className="h-dvh flex flex-col bg-slate-900 text-slate-100">
      <Header
        activeAgent={activeAgent}
        agents={agents}
        onAgentSwitch={handleAgentSwitch}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
      />
      <MessageList
        messages={displayMessages}
        streamingContent={streamingContent}
        isStreaming={isStreaming}
      />
      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming || isViewingHistory}
      />
    </div>
  )
}

export default App
