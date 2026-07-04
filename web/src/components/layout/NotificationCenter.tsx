import { useEffect, useRef, useState } from 'react'
import { useAlerts } from '../../hooks/useAlerts'
import { useAppearance } from '../../hooks/useAppearance'
import type { Alert } from '../../types/alerts'

type NotificationCenterProps = {
  assets: Array<{ id: number; name: string }>
  onSelectConversation: (conversationId: string) => void
  onSelectAsset: (assetId: number) => void
}

export function NotificationCenter({
  assets,
  onSelectConversation,
  onSelectAsset,
}: NotificationCenterProps) {
  const { alerts, unreadCount, resolveAlert } = useAlerts()
  const { t } = useAppearance()
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Handle clicking outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleAlertClick = (alert: Alert) => {
    if (alert.assetId) {
      onSelectAsset(alert.assetId)
    }

    if (alert.conversationId) {
      onSelectConversation(alert.conversationId)
    }

    setIsOpen(false)
  }

  const markResolved = (alertId: number) => {
    void resolveAlert(alertId)
  }

  const getSeverityStyles = (severity: string) => {
    switch (severity) {
      case 'critical':
        return {
          bg: 'bg-ops-danger/10 border-ops-danger/30',
          dot: 'bg-ops-danger',
          text: 'text-ops-danger',
        }
      case 'warning':
        return {
          bg: 'bg-ops-warning/10 border-ops-warning/30',
          dot: 'bg-ops-warning',
          text: 'text-ops-warning',
        }
      default:
        return {
          bg: 'bg-ops-green/10 border-ops-green/30',
          dot: 'bg-ops-green',
          text: 'text-ops-green',
        }
    }
  }

  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString)
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return ''
    }
  }

  const getAssetName = (assetId: number) => {
    return assets.find((a) => a.id === assetId)?.name ?? `Asset #${assetId}`
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="button flex h-8 w-8 items-center justify-center p-0 active:scale-95 relative transition-all duration-200"
        aria-label={t('alerts.open')}
      >
        <svg
          viewBox="0 0 24 24"
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 ? (
          <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-ops-danger px-1 text-[10px] font-black text-ops-text shadow-glow animate-pulse">
            {unreadCount}
          </span>
        ) : null}
      </button>

      {isOpen ? (
        <div className="absolute right-0 mt-2.5 flex max-h-[min(460px,calc(100vh-72px))] w-[calc(100vw-1rem)] max-w-80 flex-col rounded-xl border border-ops-border/25 bg-ops-panel/95 backdrop-blur-xl shadow-2xl z-[100] animate-in fade-in slide-in-from-top-3 duration-200">
          <div className="flex items-center justify-between gap-3 p-4 border-b border-ops-border/15 shrink-0 bg-ops-panel">
            <h4 className="text-xs font-bold text-ops-green tracking-wider">{t('alerts.title', { count: String(alerts.length) })}</h4>
            {unreadCount > 0 ? (
              <button
                type="button"
                onClick={() => {
                  alerts.forEach((a) => {
                    if (a.status === 'unread') void resolveAlert(a.id)
                  })
                }}
                className="button-mini h-7 shrink-0 px-2 text-[10px] text-ops-muted hover:text-ops-text"
              >
                {t('alerts.resolveAll')}
              </button>
            ) : null}
          </div>

          <div className="flex-1 overflow-y-auto max-h-[360px] custom-scrollbar p-2 space-y-2">
            {alerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center text-ops-muted/40">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className="mb-2"
                >
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <p className="text-[10px] font-bold tracking-wider">{t('alerts.empty')}</p>
              </div>
            ) : (
              alerts.map((alert) => {
                const styles = getSeverityStyles(alert.severity)
                const isUnread = alert.status === 'unread'
                return (
                  <div
                    key={alert.id}
                    onClick={() => handleAlertClick(alert)}
                    className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-150 ${
                      isUnread
                        ? `${styles.bg} hover:border-ops-green/40 shadow-sm`
                        : 'bg-ops-deep/30 border-ops-border/10 hover:border-ops-border/20 opacity-60'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${styles.dot} ${isUnread ? 'animate-pulse' : ''}`} />
                        <span className={`text-[11px] font-black truncate leading-tight ${isUnread ? 'text-ops-text' : 'text-ops-muted'}`}>
                          {alert.title}
                        </span>
                      </div>
                      <span className="text-[10px] font-bold text-ops-muted shrink-0">
                        {formatTime(alert.createdAt)}
                      </span>
                    </div>

                    <p className="text-[10px] text-ops-muted font-medium mt-1 leading-normal break-all line-clamp-2">
                      {alert.message}
                    </p>

                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-ops-border/10">
                      <span className="min-w-0 truncate text-[10px] font-bold text-ops-green/85">
                        {getAssetName(alert.assetId)}
                      </span>
                      <div className="flex shrink-0 items-center gap-2">
                        {isUnread ? (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              markResolved(alert.id)
                            }}
                            className="text-[10px] font-black text-ops-muted hover:text-ops-text transition-colors"
                          >
                            {t('alerts.markRead')}
                          </button>
                        ) : null}
                        {alert.conversationId ? (
                          <span className="inline-flex items-center gap-0.5 text-[10px] font-black text-ops-green hover:underline">
                            {alert.severity === 'critical' ? t('alerts.handleApproval') : t('alerts.openConversation')}
                            <svg viewBox="0 0 24 24" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2.5">
                              <path d="M5 12h14M12 5l7 7-7 7" />
                            </svg>
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
