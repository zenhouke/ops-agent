import { useEffect, useState } from 'react'
import { getConsoleBootstrap } from '../../api'
import type { ConsoleBootstrap } from '../../types/api'

const emptyBootstrap: ConsoleBootstrap = {
  assets: [],
  groups: [],
  historyByAsset: {},
  modelOptions: [],
  terminalSessionId: null,
  terminalSessionChannel: null,
  terminalSessionError: '',
  initialPrompt: '',
  terminalOutput: '',
  initialEvents: [],
  sshKeys: [],
}

export function useConsoleBootstrap() {
  const [bootstrap, setBootstrap] = useState<ConsoleBootstrap>(emptyBootstrap)
  const [isBootstrapLoaded, setIsBootstrapLoaded] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [prompt, setPrompt] = useState(() => {
    return localStorage.getItem('ops_agent_prompt') ?? ''
  })
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    localStorage.setItem('ops_agent_prompt', prompt)
  }, [prompt])

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const data = await getConsoleBootstrap()
        if (!active) {
          return
        }
        setBootstrap(data)
        setSelectedModel((current) => current || data.modelOptions[0] || '')
        if (!localStorage.getItem('ops_agent_prompt') && data.initialPrompt) {
          setPrompt(data.initialPrompt)
        }
        setIsBootstrapLoaded(true)
        setLoadError(null)
      } catch (error: unknown) {
        if (!active) {
          return
        }
        setLoadError(
          error instanceof Error
            ? `Failed to load console bootstrap: ${error.message}`
            : 'Failed to load console bootstrap.'
        )
      }
    }

    void load()
    const handleAssetsChanged = () => { void load() }
    window.addEventListener('ops-agent:assets-changed', handleAssetsChanged)

    return () => {
      active = false
      window.removeEventListener('ops-agent:assets-changed', handleAssetsChanged)
    }
  }, [])

  return {
    bootstrap,
    isBootstrapLoaded,
    setBootstrap,
    selectedModel,
    setSelectedModel,
    prompt,
    setPrompt,
    loadError,
    setLoadError,
  }
}
