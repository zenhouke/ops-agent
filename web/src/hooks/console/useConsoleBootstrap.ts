import { useEffect, useState } from 'react'
import { getConsoleBootstrap } from '../../api'
import type { ConsoleBootstrap } from '../../types/api'

const emptyBootstrap: ConsoleBootstrap = {
  assets: [],
  groups: [],
  historyByAsset: {},
  modelOptions: [],
  selectedModel: '',
  modelConfigured: false,
  modelConfigurationMessage: 'LLM 模型未配置，请先在设置中添加并设为默认模型。',
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

    void (async () => {
      try {
        const data = await getConsoleBootstrap()
        if (!active) {
          return
        }
        setBootstrap(data)
        setSelectedModel(data.selectedModel || data.modelOptions[0] || '')
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
    })()

    return () => {
      active = false
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
