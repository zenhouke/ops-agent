import { useEffect, useState } from 'react'
import { getAlerts, updateAlertStatus } from '../api'
import { requestEventStream } from '../api/client'
import type { Alert, AlertStatus } from '../types/alerts'

type AlertStreamEvent = Alert & { type: 'new_alert' }
type AlertUpdateStreamEvent = { type: 'alert_updated'; id: number; status: AlertStatus }

async function readAlertStream(
  response: Response,
  onEvent: (event: AlertStreamEvent | AlertUpdateStreamEvent) => void,
) {
  const reader = response.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('\n')
      if (data) onEvent(JSON.parse(data) as AlertStreamEvent | AlertUpdateStreamEvent)
    }
  }
}

export function useAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const abortController = new AbortController()

    const initSSE = async () => {
      try {
        const response = await requestEventStream('/api/alerts/sse', {
          signal: abortController.signal,
        })
        await readAlertStream(response, (data) => {
          if (!active) return
          if (data.type === 'new_alert') {
            setAlerts((prev) => {
              if (prev.some((a) => a.id === data.id)) return prev
              return [data, ...prev]
            })
            return
          }
          setAlerts((prev) =>
            prev.map((a) => (a.id === data.id ? { ...a, status: data.status } : a))
          )
        })
      } catch (err) {
        if (!abortController.signal.aborted) {
          console.error('Failed to initialize Alerts SSE:', err)
        }
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
      abortController.abort()
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
