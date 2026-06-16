import { requestJson, requestVoid } from './client'
import type { Alert, AlertSeverity, AlertStatus, ScheduledJob } from '../types/alerts'

type AlertDto = {
  id: number
  job_id: number | null
  asset_id: number
  runtime_id: string | null
  conversation_id: string | null
  severity: AlertSeverity
  title: string
  message: string
  status: AlertStatus
  created_at: string
  updated_at: string
}

type ScheduledJobDto = {
  id: number
  name: string
  asset_id: number
  prompt: string
  interval_seconds: number
  enabled: boolean
  last_run_at: string | null
  created_at: string
  updated_at: string
}

export function mapAlert(dto: AlertDto): Alert {
  return {
    id: dto.id,
    jobId: dto.job_id,
    assetId: dto.asset_id,
    runtimeId: dto.runtime_id,
    conversationId: dto.conversation_id,
    severity: dto.severity,
    title: dto.title,
    message: dto.message,
    status: dto.status,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export function mapScheduledJob(dto: ScheduledJobDto): ScheduledJob {
  return {
    id: dto.id,
    name: dto.name,
    assetId: dto.asset_id,
    prompt: dto.prompt,
    intervalSeconds: dto.interval_seconds,
    enabled: dto.enabled,
    lastRunAt: dto.last_run_at,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export async function getAlerts(status?: string): Promise<Alert[]> {
  const query = status ? `?status=${status}` : ''
  const alerts = await requestJson<AlertDto[]>(`/api/alerts${query}`)
  return alerts.map(mapAlert)
}

export async function updateAlertStatus(alertId: number, status: string): Promise<Alert> {
  const alert = await requestJson<AlertDto>(`/api/alerts/${alertId}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  })
  return mapAlert(alert)
}

export async function getScheduledJobs(): Promise<ScheduledJob[]> {
  const jobs = await requestJson<ScheduledJobDto[]>('/api/scheduler/jobs')
  return jobs.map(mapScheduledJob)
}

export async function createScheduledJob(payload: {
  name: string
  asset_id: number
  prompt: string
  interval_seconds: number
  enabled: boolean
}): Promise<ScheduledJob> {
  const job = await requestJson<ScheduledJobDto>('/api/scheduler/jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapScheduledJob(job)
}

export async function updateScheduledJob(
  jobId: number,
  payload: {
    name?: string
    asset_id?: number
    prompt?: string
    interval_seconds?: number
    enabled?: boolean
  }
): Promise<ScheduledJob> {
  const job = await requestJson<ScheduledJobDto>(`/api/scheduler/jobs/${jobId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return mapScheduledJob(job)
}

export async function deleteScheduledJob(jobId: number): Promise<void> {
  return requestVoid(`/api/scheduler/jobs/${jobId}`, {
    method: 'DELETE',
  })
}

export async function triggerScheduledJob(jobId: number): Promise<void> {
  return requestVoid(`/api/scheduler/jobs/${jobId}/trigger`, {
    method: 'POST',
  })
}
