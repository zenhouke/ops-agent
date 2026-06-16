import { useEffect, useState } from 'react'
import { getAlerts, updateAlertStatus } from '../api'
import { getDesktopApiBaseUrl } from '../desktop'
import type { Alert, AlertStatus } from '../types/alerts'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

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

    const initSSE = async () => {
      try {
        const baseUrl = await resolveApiBaseUrl()
        const sseUrl = `${baseUrl}/api/alerts/sse`
        eventSource = new EventSource(sseUrl)

        eventSource.addEventListener('new_alert', (e) => {
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

        eventSource.addEventListener('alert_updated', (e) => {
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

        eventSource.onerror = () => {
          // EventSource will automatically reconnect, log as info
          console.debug('Alerts SSE connection closed/errored, retrying...')
        }
      } catch (err) {
        console.error('Failed to initialize Alerts SSE:', err)
      }
    }

    // Initial load
    getAlerts()
      .then((data) => {
        if (active) {
          setAlerts(data)
          setLoading(false)
        }
      })
      .catch((err) => {
        console.error('Failed to load initial alerts:', err)
        if (active) setLoading(false)
      })

    void initSSE()

    return () => {
      active = false
      if (eventSource) {
        eventSource.close()
      }
    }
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
