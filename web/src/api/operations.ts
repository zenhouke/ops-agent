import { requestJson } from './client'

export type OperationKind = 'sync' | 'topology' | 'inspection'
export type OperationItem = { assetId: number | string; assetName: string; status: string; message: string; conversationId?: string; runtimeId?: string }
export type Operation = {
  id: string; kind: OperationKind; status: string; message: string; createdAt: string; updatedAt: string
  payload: { instanceId: number; organization?: string; prompt?: string; scheduledJobId?: number }
  total: number; completed: number; items: OperationItem[]; result: { id?: number; total?: number; created?: number; updated?: number; skipped?: number } | null; retryOf: string | null
}
export const operationActive = (status: string) => ['queued', 'running', 'cancelling'].includes(status)
export const listOperations = (kind: OperationKind, instanceId?: number, organization?: string) => {
  const query = new URLSearchParams({ kind })
  if (instanceId !== undefined) query.set('instance_id', String(instanceId))
  if (organization !== undefined) query.set('organization', organization)
  return requestJson<Operation[]>(`/api/operations?${query}`)
}
export const startOperation = (payload: { kind: OperationKind; instanceId: number; organization?: string; prompt?: string; maxConcurrency?: number }) => requestJson<Operation>('/api/operations', { method: 'POST', body: JSON.stringify(payload) })
export const controlOperation = (id: string, action: 'cancel' | 'retry') => requestJson<Operation>(`/api/operations/${id}/${action}`, { method: 'POST' })
