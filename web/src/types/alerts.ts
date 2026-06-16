export type AlertSeverity = 'info' | 'warning' | 'critical'
export type AlertStatus = 'unread' | 'resolved' | 'ignored'

export type Alert = {
  id: number
  jobId: number | null
  assetId: number
  runtimeId: string | null
  conversationId: string | null
  severity: AlertSeverity
  title: string
  message: string
  status: AlertStatus
  createdAt: string
  updatedAt: string
}

export type ScheduledJob = {
  id: number
  name: string
  assetId: number
  prompt: string
  intervalSeconds: number
  enabled: boolean
  lastRunAt: string | null
  createdAt: string
  updatedAt: string
}
