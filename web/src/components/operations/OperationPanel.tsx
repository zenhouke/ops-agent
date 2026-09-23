import { useState } from 'react'
import { controlOperation, operationActive, type Operation } from '../../api/operations'

const labels: Record<string, string> = { queued: '等待执行', running: '执行中', cancelling: '取消中', cancelled: '已取消', interrupted: '已中断', completed: '已完成', failed: '失败', partial: '部分完成', waiting_approval: '等待审批', waiting_input: '等待回复', resuming: '继续执行中', skipped: '已跳过', warning: '发现异常' }
export function OperationPanel({ operation, onRefresh, onOpenConversation, onOpenResult }: { operation: Operation; onRefresh: () => void; onOpenConversation?: (id: string) => void; onOpenResult?: (id: number) => void }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const act = async (action: 'cancel' | 'retry') => {
    setBusy(true); setError('')
    try { await controlOperation(operation.id, action); onRefresh() }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }
  const report = () => {
    const blob = new Blob([JSON.stringify({ kind: operation.kind, organization: operation.payload.organization, createdAt: operation.createdAt, status: operation.status, total: operation.total, completed: operation.completed, devices: operation.items, result: operation.result }, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a'); link.href = url; link.download = `${operation.kind}-${operation.id}.json`; link.click(); URL.revokeObjectURL(url)
  }
  return <div className="rounded border border-ops-border/35 bg-ops-deep/40 p-3 text-[11px]">
    <div className="flex flex-wrap items-center justify-between gap-2"><strong>{labels[operation.status] ?? operation.status} · {operation.completed}/{operation.total}</strong><time className="text-ops-muted">{new Date(operation.createdAt).toLocaleString()}</time></div>
    <p className="my-2 break-words text-ops-muted">{operation.message}</p>
    <progress className="h-1.5 w-full accent-cyan-400" aria-label="任务进度" value={operation.completed} max={Math.max(operation.total, 1)} />
    {operation.kind === 'sync' && operation.result ? <p className="my-2">读取 {operation.result.total}，新增 {operation.result.created}，更新 {operation.result.updated}，跳过 {operation.result.skipped}</p> : null}
    <div className="mt-2 flex flex-wrap gap-2">
      {operationActive(operation.status) ? <button className="button" disabled={busy || operation.status === 'cancelling'} onClick={() => void act('cancel')}>取消后续操作</button> : null}
      {['failed', 'partial', 'cancelled', 'interrupted'].includes(operation.status) ? <button className="button" disabled={busy || (operation.kind !== 'sync' && operation.items.length > 0 && !operation.items.some((item) => ['failed', 'cancelled', 'interrupted', 'queued', 'running'].includes(item.status)))} onClick={() => void act('retry')}>{operation.kind === 'sync' ? '重新完整同步' : '重试未完成项'}</button> : null}
      {operation.result?.id && onOpenResult ? <button className="button" onClick={() => onOpenResult(operation.result!.id!)}>查看拓扑结果</button> : null}
      <button className="button" onClick={report}>下载{operation.kind === 'inspection' ? '巡检报告' : '任务结果'}</button>
    </div>
    {error ? <p role="alert" className="mt-2 text-ops-danger">{error}</p> : null}
    <details className="mt-2"><summary className="cursor-pointer text-ops-cyan">逐设备结果 / 异常清单（{operation.items.filter((item) => !['completed', 'skipped'].includes(item.status)).length}）</summary><div className="mt-2 max-h-80 space-y-2 overflow-auto">{operation.items.map((item) => <div key={item.assetId} className="border-t border-ops-border/25 pt-2"><div className="flex justify-between gap-2"><span>{item.assetName}</span><span>{labels[item.status] ?? item.status}</span></div><p className="whitespace-pre-wrap break-words text-ops-muted">{item.message}</p>{item.conversationId && onOpenConversation ? <button className="mt-1 text-ops-cyan" onClick={() => onOpenConversation(item.conversationId!)}>打开设备任务 / 处理审批</button> : null}</div>)}</div></details>
  </div>
}
