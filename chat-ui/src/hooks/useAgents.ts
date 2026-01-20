import { useState, useEffect } from 'react'
import { getAgents, switchAgent as apiSwitchAgent, type Agent } from '@/api/client'

export interface UseAgentsReturn {
  agents: Agent[]
  activeAgent: string | null
  switchAgent: (name: string) => Promise<void>
  isLoading: boolean
  error: string | null
}

export function useAgents(): UseAgentsReturn {
  const [agents, setAgents] = useState<Agent[]>([])
  const [activeAgent, setActiveAgent] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      setIsLoading(true)
      const data = await getAgents()
      setAgents(data)
      const active = data.find((a) => a.active)
      setActiveAgent(active?.name || 'default')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agents')
    } finally {
      setIsLoading(false)
    }
  }

  const switchAgent = async (name: string) => {
    try {
      await apiSwitchAgent(name)
      setActiveAgent(name)
      // Update agents list
      setAgents((prev) =>
        prev.map((a) => ({
          ...a,
          active: a.name === name,
        }))
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to switch agent')
      throw err
    }
  }

  return {
    agents,
    activeAgent,
    switchAgent,
    isLoading,
    error,
  }
}
