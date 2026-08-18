import type { Asset, ConversationContextStatus, RuntimeSnapshot } from '../../types/ops'

type StatusBarProps = {
  asset: Asset | null
  model: string
  contextStatus: ConversationContextStatus | null
  runtime: RuntimeSnapshot | null
  isRunActive?: boolean
  hasPendingApproval?: boolean
  terminalCount: number
}

function runtimeLabel(runtime: RuntimeSnapshot | null, isRunActive = false, hasPendingApproval = false) {
  if (!runtime) {
    if (hasPendingApproval) return '等待审批'
    return isRunActive ? '执行中' : '就绪'
  }
  const status = `${runtime.runState || ''} ${runtime.status || ''}`.toLowerCase()
  if (status.includes('complete') || status.includes('success')) return '已完成'
  if (status.includes('fail') || status.includes('error') || status.includes('interrupt')) return '执行失败'
  if (hasPendingApproval || runtime.pendingApprovalStepId) return '等待审批'
  if (isRunActive) return '执行中'
  return '执行中'
}

export function StatusBar({ asset, model, contextStatus, runtime, isRunActive = false, hasPendingApproval = false, terminalCount }: StatusBarProps) {
  const targetLabel = asset?.host || asset?.name || '未选择'
  const runtimeStatus = `${runtime?.runState || ''} ${runtime?.status || ''}`.toLowerCase()
  const isTerminal = /complete|success|fail|error|interrupt/.test(runtimeStatus)

  return (
    <footer className="desktop-status-bar" aria-label="Application status">
      <div className="desktop-status-primary">
        <span className="h-1.5 w-1.5 rounded-full bg-ops-green" />
        服务已连接
      </div>
      <div className="desktop-status-item">
        <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M4 17 10 11 4 5M12 19h8" />
        </svg>
        {terminalCount} 个终端
      </div>
      <div className="desktop-status-item max-w-[240px]" title={targetLabel}>
        目标：<span className="truncate font-medium text-ops-text/85">{targetLabel}</span>
      </div>
      <div className="desktop-status-item max-w-[220px]" title={runtimeLabel(runtime, isRunActive, hasPendingApproval)}>
        <span className={hasPendingApproval || (runtime?.pendingApprovalStepId && !isTerminal) ? 'text-ops-warning' : 'text-ops-muted'}>{runtimeLabel(runtime, isRunActive, hasPendingApproval)}</span>
      </div>
      <div className="ml-auto desktop-status-item font-mono">
        上下文 {contextStatus ? `${Math.round(contextStatus.contextPercent)}%` : '--'}
      </div>
      <div className="desktop-status-item max-w-[220px]" title={model}>
        <span className="truncate">{model || '未选择模型'}</span>
      </div>
    </footer>
  )
}
