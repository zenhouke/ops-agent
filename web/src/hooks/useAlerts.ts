import { useEffect, useState } from 'react'
import { getAlerts, updateAlertStatus } from '../api'
import { getDesktopApiBaseUrl } from '../desktop'
import type { Alert, AlertStatus } from '../types/alerts'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const alertInitialLoadRetryDelaysMs = [1000, 2000, 5000, 10000, 30000]
const alertSseReconnectDelaysMs = [10000, 15000, 30000]
const alertSseCleanups = new Set<() => void>()

import.meta.hot?.dispose(() => {
  for (const cleanup of alertSseCleanups) {
    cleanup()
  }
  alertSseCleanups.clear()
})

function retryDelay(delays: number[], attempt: number) {
  return delays[Math.min(attempt, delays.length - 1)]
}

async function resolveApiBaseUrl() {
  const desktopBaseUrl = await getDesktopApiBaseUrl()
  if (desktopBaseUrl) {
    return desktopBaseUrl
  }
  return API_BASE_URL
}

export function useAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    let eventSource: EventSource | null = null
    let sseReconnectTimer: ReturnType<typeof setTimeout> | null = null
    let initialLoadTimer: ReturnType<typeof setTimeout> | null = null
    let sseReconnectAttempt = 0
    let initialLoadAttempt = 0

    const clearSseReconnect = () => {
      if (sseReconnectTimer) {
        window.clearTimeout(sseReconnectTimer)
        sseReconnectTimer = null
      }
    }

    const scheduleSseReconnect = () => {
      if (!active || sseReconnectTimer) {
        return
      }
      const delay = retryDelay(alertSseReconnectDelaysMs, sseReconnectAttempt)
      sseReconnectAttempt += 1
      sseReconnectTimer = window.setTimeout(() => {
        sseReconnectTimer = null
        void initSSE()
      }, delay)
    }

    const initSSE = async () => {
      try {
        const baseUrl = await resolveApiBaseUrl()
        if (!active) return
        const sseUrl = `${baseUrl}/api/alerts/sse`
        const source = new EventSource(sseUrl)
        eventSource = source

        source.onopen = () => {
          sseReconnectAttempt = 0
        }

        source.addEventListener('new_alert', (e) => {
          if (!active) return
          try {
            const data = JSON.parse(e.data) as Alert
            setAlerts((prev) => {
              if (prev.some((a) => a.id === data.id)) return prev
              return [data, ...prev]
            })
          } catch (err) {
            console.error('Failed to parse SSE new_alert event data:', err)
          }
        })

        source.addEventListener('alert_updated', (e) => {
          if (!active) return
          try {
            const data = JSON.parse(e.data) as { id: number; status: AlertStatus }
            setAlerts((prev) =>
              prev.map((a) => (a.id === data.id ? { ...a, status: data.status } : a))
            )
          } catch (err) {
            console.error('Failed to parse SSE alert_updated event data:', err)
          }
        })

        source.onerror = () => {
          if (!active) return
          eventSource?.close()
          if (eventSource === source) {
            eventSource = null
          }
          scheduleSseReconnect()
        }
      } catch (err) {
        if (!active) return
        console.debug('Alerts SSE initialization failed; retrying with backoff.', err)
        scheduleSseReconnect()
      }
    }

    const loadInitialAlerts = () => {
      getAlerts()
        .then((data) => {
          if (!active) return
          initialLoadAttempt = 0
          setAlerts(data)
          setLoading(false)
          void initSSE()
        })
        .catch((err) => {
          if (!active) return
          console.debug('Failed to load initial alerts; retrying with backoff.', err)
          setLoading(false)
          const delay = retryDelay(alertInitialLoadRetryDelaysMs, initialLoadAttempt)
          initialLoadAttempt += 1
          initialLoadTimer = window.setTimeout(() => {
            initialLoadTimer = null
            loadInitialAlerts()
          }, delay)
        })
    }

    const cleanup = () => {
      active = false
      alertSseCleanups.delete(cleanup)
      clearSseReconnect()
      if (initialLoadTimer) {
        window.clearTimeout(initialLoadTimer)
        initialLoadTimer = null
      }
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
    }

    alertSseCleanups.add(cleanup)
    loadInitialAlerts()

    return cleanup
  }, [])

  const resolveAlert = async (id: number) => {
    try {
      await updateAlertStatus(id, 'resolved')
      // Local state is updated via the SSE 'alert_updated' event,
      // but we update it here as well for immediate responsiveness.
      setAlerts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, status: 'resolved' as AlertStatus } : a))
      )
    } catch (err) {
      console.error('Failed to resolve alert:', err)
      throw err
    }
  }

  const unreadAlerts = alerts.filter((a) => a.status === 'unread')
  const unreadCount = unreadAlerts.length

  return {
    alerts,
    unreadAlerts,
    unreadCount,
    loading,
    resolveAlert,
  }
}
