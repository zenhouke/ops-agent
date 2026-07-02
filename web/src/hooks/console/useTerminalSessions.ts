import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  closeTerminalSession as closeTerminalSessionApi,
  createTerminalSession,
  reconnectTerminalSession,
} from '../../api'
import type { Asset } from '../../types/ops'
import { stripAnsi } from '../../components/assistant/conversation/utils'
import {
  defaultLocalTerminalAsset,
  LOCAL_TERMINAL_ASSET_ID,
} from './consoleShared'
import {
  buildRestoredTerminalState,
  persistTerminalState,
  readPersistedTerminalState,
  type TerminalTabState,
} from './terminalSessionPersistence'
import { useTerminalSockets } from './useTerminalSockets'

type TerminalTab = TerminalTabState

interface UseTerminalSessionsProps {
  assets: Asset[]
  historyByAsset: Record<number, any[]>
  setLoadError: (error: string | null) => void
}

export function useTerminalSessions({
  assets,
  historyByAsset,
  setLoadError,
}: UseTerminalSessionsProps) {
  const [terminalTabs, setTerminalTabs] = useState<TerminalTab[]>([
    {
      assetId: LOCAL_TERMINAL_ASSET_ID,
      asset: defaultLocalTerminalAsset,
      sessionId: null,
      output: '',
    },
  ])
  const [activeTerminalAssetId, setActiveTerminalAssetId] = useState<number>(
    LOCAL_TERMINAL_ASSET_ID
  )

  const terminalSocketsRef = useRef<Record<number, WebSocket | undefined>>({})
  const terminalSessionIdsRef = useRef<Record<number, string | null>>({
    [LOCAL_TERMINAL_ASSET_ID]: null,
  })
  const terminalTabsRef = useRef<TerminalTab[]>([
    {
      assetId: LOCAL_TERMINAL_ASSET_ID,
      asset: defaultLocalTerminalAsset,
      sessionId: null,
      output: '',
    },
  ])
  const terminalSocketRef = useRef<WebSocket | null>(null)
  const hasRestoredTerminalStateRef = useRef(false)
  const firstOutputHandledRef = useRef<Record<number, boolean>>({
    [LOCAL_TERMINAL_ASSET_ID]: false,
  })
  const restoredAssetIdsRef = useRef<Set<number>>(new Set())
  const reconnectingRestoredAssetsRef = useRef<Set<number>>(new Set())

  const syncTerminalTabs = useCallback(
    (updater: (currentTabs: TerminalTab[]) => TerminalTab[]) => {
      setTerminalTabs((currentTabs) => {
        const nextTabs = updater(currentTabs)
        terminalTabsRef.current = nextTabs
        terminalSessionIdsRef.current = Object.fromEntries(
          nextTabs.map((tab) => [tab.assetId, tab.sessionId])
        )
        return nextTabs
      })
    },
    []
  )

  const initializeLocalTerminal = useCallback(
    (terminalSessionId: string | null, terminalOutput: string, terminalError = '') => {
      const initialOutput = terminalSessionId === null && terminalError
        ? `\r\n\x1b[31m[ERROR] ${terminalError}\x1b[0m\r\n`
        : terminalOutput
      const restoredState = buildRestoredTerminalState({
        assets,
        localSessionId: terminalSessionId,
        localOutput: initialOutput,
        persisted: readPersistedTerminalState(),
      })
      setTerminalTabs(restoredState.tabs)
      terminalTabsRef.current = restoredState.tabs
      terminalSessionIdsRef.current = Object.fromEntries(
        restoredState.tabs.map((tab) => [tab.assetId, tab.sessionId])
      )
      restoredAssetIdsRef.current = new Set(
        restoredState.tabs
          .filter((tab) => tab.assetId !== LOCAL_TERMINAL_ASSET_ID && tab.sessionId === null)
          .map((tab) => tab.assetId)
      )
      for (const tab of restoredState.tabs) {
        firstOutputHandledRef.current[tab.assetId] = false
      }
      setActiveTerminalAssetId(restoredState.activeAssetId)
      hasRestoredTerminalStateRef.current = true
    },
    [assets]
  )

  const connectAssetTerminal = useCallback(async (asset: Asset) => {
      if (asset.id === LOCAL_TERMINAL_ASSET_ID) {
        setActiveTerminalAssetId(LOCAL_TERMINAL_ASSET_ID)
        return
      }

      setLoadError(null)
      setActiveTerminalAssetId(asset.id)

      const existingTab = terminalTabsRef.current.find(
        (item) => item.assetId === asset.id
      )
      if (existingTab) {
        return
      }

      syncTerminalTabs((currentTabs) => [
        ...currentTabs,
        { assetId: asset.id, asset, sessionId: null, output: '' },
      ])
      firstOutputHandledRef.current[asset.id] = false

      try {
        const result = await createTerminalSession(asset.id)
        if (result.error) {
          throw new Error(result.error)
        }
        if (result.terminal_id === null) {
          throw new Error('Failed to create terminal session')
        }
        syncTerminalTabs((currentTabs) =>
          currentTabs.map((tabItem) =>
            tabItem.assetId === asset.id
              ? { ...tabItem, sessionId: result.terminal_id }
              : tabItem
          )
        )
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to connect to asset terminal'
        setLoadError(errorMessage)

        syncTerminalTabs((currentTabs) =>
          currentTabs.map((tabItem) =>
            tabItem.assetId === asset.id
              ? {
                  ...tabItem,
                  output: `\r\n\x1b[31m[ERROR] ${errorMessage}\x1b[0m\r\n`,
                }
              : tabItem
          )
        )
      }
    },
    [syncTerminalTabs, setLoadError]
  )

  const removeTerminalTab = useCallback(
    (assetId: number) => {
      const tab = terminalTabsRef.current.find((item) => item.assetId === assetId)
      const socket = terminalSocketsRef.current[assetId]
      delete terminalSocketsRef.current[assetId]
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close()
      }
      if (tab?.sessionId) {
        void closeTerminalSessionApi(tab.sessionId).catch(() => undefined)
      }
      delete terminalSessionIdsRef.current[assetId]
      delete firstOutputHandledRef.current[assetId]
      restoredAssetIdsRef.current.delete(assetId)
      reconnectingRestoredAssetsRef.current.delete(assetId)

      syncTerminalTabs((currentTabs) =>
        currentTabs.filter((item) => item.assetId !== assetId)
      )
      setActiveTerminalAssetId((currentId) =>
        currentId === assetId ? LOCAL_TERMINAL_ASSET_ID : currentId
      )
    },
    [syncTerminalTabs]
  )

  const clearActiveTerminal = useCallback(() => {
    syncTerminalTabs((currentTabs) =>
      currentTabs.map((tab) =>
        tab.assetId === activeTerminalAssetId ? { ...tab, output: '' } : tab
      )
    )
    firstOutputHandledRef.current[activeTerminalAssetId] = true
  }, [activeTerminalAssetId, syncTerminalTabs])

  const copyActiveTerminalOutput = useCallback(async (): Promise<boolean> => {
    const tab = terminalTabsRef.current.find((item) => item.assetId === activeTerminalAssetId)
    const raw = tab?.output ?? ''
    if (!raw) return false
    const cleaned = stripAnsi(raw)
    try {
      await navigator.clipboard.writeText(cleaned)
      return true
    } catch {
      return false
    }
  }, [activeTerminalAssetId])

  const reconnectActiveTerminal = useCallback(async () => {
    const tab = terminalTabsRef.current.find((item) => item.assetId === activeTerminalAssetId)
    if (!tab) return
    const existingSocket = terminalSocketsRef.current[activeTerminalAssetId]
    if (existingSocket && (existingSocket.readyState === WebSocket.OPEN || existingSocket.readyState === WebSocket.CONNECTING)) {
      existingSocket.close()
    }
    delete terminalSocketsRef.current[activeTerminalAssetId]
    if (terminalSocketRef.current === existingSocket) {
      terminalSocketRef.current = null
    }

    syncTerminalTabs((currentTabs) =>
      currentTabs.map((item) =>
        item.assetId === activeTerminalAssetId ? { ...item, sessionId: null, output: '' } : item
      )
    )
    firstOutputHandledRef.current[activeTerminalAssetId] = false

    try {
      let nextSessionId: string | null = null
      if (tab.sessionId) {
        const result = await reconnectTerminalSession(tab.sessionId, activeTerminalAssetId)
        if (result.error || !result.terminal_id) {
          throw new Error(result.error || 'Reconnection failed')
        }
        nextSessionId = result.terminal_id
      } else {
        const result = await createTerminalSession(activeTerminalAssetId)
        if (result.error || !result.terminal_id) {
          throw new Error(result.error || 'Reconnection failed')
        }
        nextSessionId = result.terminal_id
      }
      syncTerminalTabs((currentTabs) =>
        currentTabs.map((item) =>
          item.assetId === activeTerminalAssetId ? { ...item, sessionId: nextSessionId } : item
        )
      )
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Terminal reconnection failed'
      setLoadError(errorMessage)
    }
  }, [activeTerminalAssetId, syncTerminalTabs, setLoadError])

  const selectedAsset = useMemo(
    () =>
      terminalTabs.find((item) => item.assetId === activeTerminalAssetId)
        ?.asset ?? defaultLocalTerminalAsset,
    [activeTerminalAssetId, terminalTabs]
  )

  const activeTerminalTab = useMemo(
    () =>
      terminalTabs.find((item) => item.assetId === activeTerminalAssetId) ??
      terminalTabs[0],
    [activeTerminalAssetId, terminalTabs]
  )

  const history = selectedAsset ? historyByAsset[selectedAsset.id] ?? [] : []
  const { sendTerminalInput, resizeTerminal } = useTerminalSockets({
    terminalTabs,
    activeTerminalAssetId,
    terminalSocketsRef,
    activeSocketRef: terminalSocketRef,
    firstOutputHandledRef,
    syncTerminalTabs,
    setLoadError,
  })

  const selectAsset = useCallback(
    (assetId: number) => {
      setLoadError(null)
      if (assetId === LOCAL_TERMINAL_ASSET_ID) {
        setActiveTerminalAssetId(LOCAL_TERMINAL_ASSET_ID)
        return
      }
      const asset = assets.find((item) => item.id === assetId)
      if (!asset) {
        return
      }
      void connectAssetTerminal(asset)
    },
    [assets, connectAssetTerminal, setLoadError]
  )

  useEffect(() => {
    if (!hasRestoredTerminalStateRef.current) {
      return
    }

    for (const tab of terminalTabs) {
      if (
        tab.assetId === LOCAL_TERMINAL_ASSET_ID ||
        tab.sessionId !== null ||
        !restoredAssetIdsRef.current.has(tab.assetId) ||
        reconnectingRestoredAssetsRef.current.has(tab.assetId)
      ) {
        continue
      }

      reconnectingRestoredAssetsRef.current.add(tab.assetId)
      void createTerminalSession(tab.assetId)
        .then((result) => {
          if (result.error || !result.terminal_id) {
            throw new Error(result.error || 'Terminal reconnection failed')
          }
          restoredAssetIdsRef.current.delete(tab.assetId)
          syncTerminalTabs((currentTabs) =>
            currentTabs.map((item) =>
              item.assetId === tab.assetId ? { ...item, sessionId: result.terminal_id } : item
            )
          )
        })
        .catch((error) => {
          const errorMessage = error instanceof Error ? error.message : 'Terminal reconnection failed'
          setLoadError(errorMessage)
          reconnectingRestoredAssetsRef.current.delete(tab.assetId)
        })
    }

    const hasPendingRestoredTabs = terminalTabs.some(
      (tab) => tab.sessionId === null && restoredAssetIdsRef.current.has(tab.assetId)
    )
    if (!hasPendingRestoredTabs) {
      persistTerminalState(terminalTabs, activeTerminalAssetId)
    }
  }, [activeTerminalAssetId, syncTerminalTabs, terminalTabs, setLoadError])

  return {
    terminalTabs,
    activeTerminalAssetId,
    setActiveTerminalAssetId,
    selectedAsset,
    activeTerminalTab,
    history,
    connectAssetTerminal,
    removeTerminalTab,
    sendTerminalInput,
    resizeTerminal,
    initializeLocalTerminal,
    selectAsset,
    clearActiveTerminal,
    copyActiveTerminalOutput,
    reconnectActiveTerminal,
  }
}
