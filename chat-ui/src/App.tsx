import { useState } from 'react'
import { Header } from '@/components/layout/Header'
import { MessageList } from '@/components/chat/MessageList'
import { ChatInput } from '@/components/chat/ChatInput'
import { useChat } from '@/hooks/useChat'
import { useAgents } from '@/hooks/useAgents'
import { useTheme } from '@/hooks/useTheme'
import { useConversations } from '@/hooks/useConversations'

function App() {
  useTheme() // Initialize dark mode

  const { agents, activeAgent, switchAgent } = useAgents()
  const [viewingHistoricalConversation, setViewingHistoricalConversation] = useState(false)
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
    setViewingHistoricalConversation(false)
  }

  const handleSelectConversation = async (conversationId: string) => {
    const conversation = await loadConversation(conversationId)
    if (conversation) {
      // Convert conversation messages to MessageData format
      // For now, just log it - full implementation would set read-only mode
      console.log('Load conversation:', conversation)
      setViewingHistoricalConversation(true)
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
        messages={messages}
        streamingContent={streamingContent}
        isStreaming={isStreaming}
      />
      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming || viewingHistoricalConversation}
      />
    </div>
  )
}

export default App
