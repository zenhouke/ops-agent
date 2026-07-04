import { useCallback, useEffect, useRef, type MutableRefObject } from 'react'
import { getDesktopApiBaseUrl } from '../../desktop'
import type { TerminalTabState } from './terminalSessionPersistence'
import { trimTerminalOutput } from './terminalSessionPersistence'
import { buildTerminalWebSocketUrl } from './consoleShared'

const INTERNAL_COMMAND_OUTPUT_MARKERS = [
  '__OPS_AGENT_EXIT_STATUS_',
  '$__opsAgent',
]

function filterInternalCommandOutput(value: string): string {
  const lines = value.match(/[^\r\n]*(?:\r\n|\n|\r)?/g) ?? []
  return lines
    .filter((line) => line.length > 0)
    .filter((line) => !INTERNAL_COMMAND_OUTPUT_MARKERS.some((marker) => line.includes(marker)))
    .join('')
}

type UseTerminalSocketsProps = {
  terminalTabs: TerminalTabState[]
  activeTerminalAssetId: number
  terminalSocketsRef: MutableRefObject<Record<number, WebSocket | undefined>>
  activeSocketRef: MutableRefObject<WebSocket | null>
  firstOutputHandledRef: MutableRefObject<Record<number, boolean>>
  syncTerminalTabs: (updater: (currentTabs: TerminalTabState[]) => TerminalTabState[]) => void
  setLoadError: (error: string | null) => void
}

export function useTerminalSockets({
  terminalTabs,
  activeTerminalAssetId,
  terminalSocketsRef,
  activeSocketRef,
  firstOutputHandledRef,
  syncTerminalTabs,
  setLoadError,
}: UseTerminalSocketsProps) {
  const lastTerminalSizeRef = useRef<{ cols: number; rows: number } | null>(null)
  const runtimeApiBaseUrlRef = useRef<string | null>(null)

  useEffect(() => {
    let active = true
    void getDesktopApiBaseUrl().then((baseUrl) => {
      if (active) {
        runtimeApiBaseUrlRef.current = baseUrl
      }
    })
    return () => {
      active = false
    }
  }, [])

  const sendTerminalInput = useCallback((data: string) => {
    const socket = activeSocketRef.current
    if (socket?.readyState !== WebSocket.OPEN) {
      return
    }
    socket.send(JSON.stringify({ type: 'input', data }))
  }, [activeSocketRef])

  const resizeTerminal = useCallback((cols: number, rows: number) => {
    lastTerminalSizeRef.current = { cols, rows }
  }, [])

  useEffect(() => {
    const currentSockets = terminalSocketsRef.current
    const activeTab = terminalTabs.find(
      (item) => item.assetId === activeTerminalAssetId
    )
    activeSocketRef.current =
      activeTab?.sessionId !== null && activeTab?.sessionId !== undefined
        ? (currentSockets[activeTerminalAssetId] ?? null)
        : null

    for (const tabItem of terminalTabs) {
      if (tabItem.sessionId === null || currentSockets[tabItem.assetId]) {
        continue
      }

      const socket = new WebSocket(buildTerminalWebSocketUrl(tabItem.sessionId, runtimeApiBaseUrlRef.current))
      currentSockets[tabItem.assetId] = socket
      if (tabItem.assetId === activeTerminalAssetId) {
        activeSocketRef.current = socket
      }

      socket.addEventListener('open', () => {
        if (tabItem.assetId === activeTerminalAssetId) {
          activeSocketRef.current = socket
        }
        if (lastTerminalSizeRef.current) {
          socket.send(JSON.stringify({ type: 'resize', ...lastTerminalSizeRef.current }))
        }
      })

      socket.addEventListener('message', (event) => {
        try {
          const payload = JSON.parse(event.data) as {
            type?: string
            data?: string
            message?: string
          }

          if (payload.type === 'output') {
            const incomingOutput = filterInternalCommandOutput(payload.data ?? '')
            if (incomingOutput.length === 0) {
              return
            }
            syncTerminalTabs((currentTabs) =>
              currentTabs.map((item) => {
                if (item.assetId !== tabItem.assetId) {
                  return item
                }

                const firstHandled = firstOutputHandledRef.current[tabItem.assetId] ?? false
                if (!firstHandled) {
                  firstOutputHandledRef.current[tabItem.assetId] = true
                  if (incomingOutput.length > 0 && item.output.endsWith(incomingOutput)) {
                    return item
                  }
                  if (incomingOutput.length > 0 && incomingOutput.endsWith(item.output)) {
                    return { ...item, output: trimTerminalOutput(incomingOutput) }
                  }
                }

                return { ...item, output: trimTerminalOutput(`${item.output}${incomingOutput}`) }
              })
            )
            return
          }

          if (payload.type === 'error') {
            setLoadError(payload.message ?? 'Terminal session error.')
          }
        } catch {
          const incomingOutput = filterInternalCommandOutput(String(event.data))
          if (!incomingOutput) {
            return
          }
          syncTerminalTabs((currentTabs) =>
            currentTabs.map((item) =>
              item.assetId === tabItem.assetId
                ? { ...item, output: trimTerminalOutput(`${item.output}${incomingOutput}`) }
                : item
            )
          )
        }
      })

      socket.addEventListener('error', () => {
        setLoadError('Terminal websocket connection failed.')
      })

      socket.addEventListener('close', () => {
        if (terminalSocketsRef.current[tabItem.assetId] === socket) {
          delete terminalSocketsRef.current[tabItem.assetId]
        }
        if (tabItem.assetId === activeTerminalAssetId && activeSocketRef.current === socket) {
          activeSocketRef.current = null
        }
      })
    }

    const activeAssetIds = new Set(terminalTabs.map((item) => item.assetId))
    for (const key of Object.keys(currentSockets)) {
      const assetId = Number(key)
      if (activeAssetIds.has(assetId)) {
        continue
      }
      const socket = currentSockets[assetId]
      delete currentSockets[assetId]
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING)
      ) {
        socket.close()
      }
    }
  }, [activeTerminalAssetId, activeSocketRef, firstOutputHandledRef, setLoadError, syncTerminalTabs, terminalSocketsRef, terminalTabs])

  useEffect(() => {
    return () => {
      const currentSockets = terminalSocketsRef.current
      for (const key of Object.keys(currentSockets)) {
        const socket = currentSockets[Number(key)]
        delete currentSockets[Number(key)]
        if (
          socket &&
          (socket.readyState === WebSocket.OPEN ||
            socket.readyState === WebSocket.CONNECTING)
        ) {
          socket.close()
        }
      }
      activeSocketRef.current = null
    }
  }, [activeSocketRef, terminalSocketsRef])

  return {
    sendTerminalInput,
    resizeTerminal,
  }
}
