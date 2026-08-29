import type {
  Asset,
  ConversationContextStatus,
  ConversationSummary,
  EventItem,
  RuntimeSnapshot,
  RuntimeSummary,
} from '../../types/ops'
import { ConversationView } from './ConversationView'
import { PromptInput } from './PromptInput'
import { useAppearance } from '../../hooks/useAppearance'
import type { BackgroundRunState, BackgroundRunStatus, ConversationSaveStatus } from '../../hooks/console/agentRunSupport'

type AssistantPanelProps = {
  conversationSummaries: ConversationSummary[]
  activeConversationId: string | null
  activeConversationTitle: string
  conversationScopeMode: 'single' | 'multi'
  allowedAssetCount: number
  backgroundRuns: BackgroundRunState[]
  events: EventItem[]
  eventWindow: { hasMoreBefore: boolean } | null
  isLoadingOlderEvents: boolean
  pendingApprovalRuntimeId: string | null
  runtimeSummaries: RuntimeSummary[]
  activeRuntimeSnapshot: RuntimeSnapshot | null
  models: string[]
  selectedModel: string
  prompt: string
  selectedAsset: Asset
  contextStatus: ConversationContextStatus | null
  loadError: string | null
  conversationSaveStatus: ConversationSaveStatus
  terminalOpen: boolean
  onToggleTerminal: () => void
  onModelChange: (model: string) => void
  onPromptChange: (prompt: string) => void
  onViewBackgroundRun: (conversationId: string) => void
  onCreateConversation: () => void
  onCreateMultiAssetConversation: () => void
  onSelectConversation: (conversationId: string) => void
  onDeleteConversation: (conversationId: string) => void
  onRun: (prompt: string, selectedSkillName?: string | null, mode?: 'standard' | 'incident') => Promise<void>
  activeRunStatus: BackgroundRunStatus | null
  isRunActive: boolean
  onCancelRun: () => Promise<void>
  onApprove: (allowPrefix?: string, guidance?: string) => void
  onReject: (guidance?: string) => void
  onTerminalRequestDecision?: (input: { runtimeId: string; requestId: string; approvalToken: string; approved: boolean }) => Promise<void>
  onLoadOlderEvents: () => Promise<void>
  onEditRun: (eventId: string, prompt: string) => Promise<void>
  onRetryRun: (eventId: string, prompt: string) => Promise<void>
  onExtractKnowledge: () => Promise<void>
}

function backgroundRunCopy(run: BackgroundRunState) {
  if (run.status === 'needs_approval') {
    return { message: `会话「${run.title}」需要审批`, action: '前往处理', tone: 'warning' as const }
  }
  if (run.status === 'needs_input') {
    return { message: `会话「${run.title}」等待你的回复`, action: '继续对话', tone: 'warning' as const }
  }
  if (run.status === 'completed') {
    return { message: `会话「${run.title}」已完成`, action: '查看', tone: 'success' as const }
  }
  if (run.status === 'failed') {
    return { message: `会话「${run.title}」执行失败`, action: '查看', tone: 'danger' as const }
  }
  if (run.status === 'disconnected') {
    return { message: `会话「${run.title}」连接已中断，等待状态同步`, action: '重新打开', tone: 'danger' as const }
  }
  return { message: `会话「${run.title}」正在后台运行`, action: '查看', tone: 'running' as const }
}

function ExecutionPlan({ runtime, runtimeCount }: { runtime: RuntimeSnapshot; runtimeCount: number }) {
  if (runtime.steps.length === 0) return null
  const completedCount = runtime.steps.filter((step) => step.status === 'completed').length
  return (
    <details className="mx-auto mt-2 w-[calc(100%-2.5rem)] max-w-[940px] shrink-0 rounded border border-ops-border/30 bg-ops-panel/35 px-3 py-2" open={Boolean(runtime.pendingApprovalStepId)}>
      <summary className="cursor-pointer select-none text-[11px] font-semibold text-ops-text">
        执行进度 · {completedCount}/{runtime.steps.length} 完成{runtimeCount > 1 ? ` · ${runtimeCount} 次运行` : ''}
      </summary>
      <ol className="mt-2 space-y-1.5 border-t border-ops-border/20 pt-2">
        {runtime.steps.map((step, index) => (
          <li key={step.stepId} className="grid grid-cols-[18px_minmax(0,1fr)_auto] items-start gap-2 text-[11px]">
            <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-full border text-[9px] ${step.status === 'completed' ? 'border-ops-green/50 text-ops-green' : step.status === 'failed' ? 'border-ops-danger/50 text-ops-danger' : step.status === 'running' ? 'border-ops-cyan/60 text-ops-cyan' : 'border-ops-border/50 text-ops-muted'}`}>{index + 1}</span>
            <span className="min-w-0">
              <span className="block font-medium text-ops-text">{step.title}</span>
              {step.command ? <code className="mt-0.5 block truncate text-[10px] text-ops-muted">{step.command}</code> : null}
              {step.reason ? <span className="mt-0.5 block text-[10px] text-ops-muted/80">{step.reason}</span> : null}
            </span>
            <span className={`rounded border px-1.5 py-0.5 text-[9px] ${step.riskLevel === 'high' || step.riskLevel === 'critical' ? 'border-ops-danger/30 text-ops-danger' : 'border-ops-border/30 text-ops-muted'}`}>{step.status}</span>
          </li>
        ))}
      </ol>
    </details>
  )
}

function TaskStatePanel({ runtime }: { runtime: RuntimeSnapshot }) {
  const state = runtime.taskState
  const detailSections = [
    ['范围', state.scope],
    ['约束', state.constraints],
    ['验收标准', state.acceptanceCriteria],
    ['已验证事实', state.verifiedFacts],
    ['用户决策', state.decisions],
    ['未完成', state.openItems],
    ['已完成', state.completedItems],
  ] as const
  const detailCount = detailSections.reduce((count, [, items]) => count + items.length, 0)
  if (!state.goal && !state.currentRequest && detailCount === 0) return null
  return (
    <details className="mx-auto mt-2 w-[calc(100%-2.5rem)] max-w-[940px] shrink-0 rounded border border-ops-cyan/20 bg-ops-cyan/[0.035] px-3 py-2">
      <summary className="cursor-pointer select-none text-[11px] font-semibold text-ops-text">
        <span className="mr-2 text-ops-cyan">任务概览</span>
        <span className="text-ops-muted">{state.goal || state.currentRequest}</span>
      </summary>
      <div className="mt-2 grid gap-2 border-t border-ops-border/20 pt-2 text-[11px] md:grid-cols-2">
        {state.currentRequest && state.currentRequest !== state.goal ? (
          <div className="rounded border border-ops-border/20 bg-ops-deep/35 px-2.5 py-2 md:col-span-2">
            <div className="mb-1 text-[9px] font-bold tracking-[0.1em] text-ops-muted">当前请求</div>
            <div className="text-ops-text/85">{state.currentRequest}</div>
          </div>
        ) : null}
        {detailSections.map(([label, items]) => items.length > 0 ? (
          <section key={label} className="rounded border border-ops-border/20 bg-ops-deep/35 px-2.5 py-2">
            <div className="mb-1 text-[9px] font-bold tracking-[0.1em] text-ops-muted">{label}</div>
            <ul className="space-y-1 text-ops-text/78">{items.map((item) => <li key={item}>· {item}</li>)}</ul>
          </section>
        ) : null)}
      </div>
    </details>
  )
}

export function AssistantPanel({
  activeConversationTitle,
  conversationScopeMode,
  allowedAssetCount,
  backgroundRuns,
  events,
  eventWindow,
  isLoadingOlderEvents,
  pendingApprovalRuntimeId,
  runtimeSummaries,
  activeRuntimeSnapshot,
  models,
  selectedModel,
  prompt,
  selectedAsset,
  contextStatus,
  loadError,
  conversationSaveStatus,
  terminalOpen,
  onToggleTerminal,
  onModelChange,
  onPromptChange,
  onViewBackgroundRun,
  onCreateConversation,
  onCreateMultiAssetConversation,
  onSelectConversation,
  onDeleteConversation,
  onRun,
  activeRunStatus,
  isRunActive,
  onCancelRun,
  onApprove,
  onReject,
  onTerminalRequestDecision,
  onLoadOlderEvents,
  onEditRun,
  onRetryRun,
  onExtractKnowledge,
}: AssistantPanelProps) {
  const { t } = useAppearance()
  return (
    <section className="flex h-full w-full flex-col overflow-hidden bg-ops-bg" aria-label="任务工作台">
      <header className="relative z-10 flex h-10 shrink-0 items-center justify-between border-b border-ops-border/25 bg-ops-deep/75 pr-2">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <span className="flex h-10 w-9 items-center justify-center border-r border-ops-border/25 bg-ops-bg text-ops-cyan">
            <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><path d="M12 2 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6l-8-4Z" /><path d="m9 12 2 2 4-4" /></svg>
          </span>
          <h2 className="truncate text-[12px] font-semibold text-ops-text">
            {activeConversationTitle || t('assistant.unclassifiedMission')}
          </h2>
          <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${conversationScopeMode === 'multi' ? 'border-ops-warning/30 bg-ops-warning/[0.08] text-ops-warning' : 'border-ops-border/25 text-ops-muted/65'}`}>
            {conversationScopeMode === 'multi' ? `多资产 · ${allowedAssetCount} 台` : '单资产'}
          </span>
          <span className="hidden items-center gap-1.5 text-[9px] text-ops-muted/60 lg:inline-flex"><span className="h-1.5 w-1.5 rounded-full bg-ops-green" />任务工作台</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span
            className={`mr-1 text-[9px] font-semibold ${conversationSaveStatus === 'failed' ? 'text-ops-danger' : 'text-ops-muted/55'}`}
            role={conversationSaveStatus === 'failed' ? 'alert' : 'status'}
          >
            {conversationSaveStatus === 'saving' ? '保存中…' : conversationSaveStatus === 'saved' ? '已保存' : conversationSaveStatus === 'failed' ? '保存失败' : ''}
          </span>
          <button
            type="button"
            className="desktop-toolbar-button"
            onClick={onCreateMultiAssetConversation}
            title="创建需要逐台审批访问范围的多资产任务"
          >
            多资产任务
          </button>
          <button
            type="button"
            className="desktop-toolbar-button"
            disabled={events.length === 0 || isRunActive}
            onClick={() => void onExtractKnowledge()}
            title="从当前对话生成可审核的知识草稿"
          >
            提炼知识
          </button>
          <button
            type="button"
            className={`desktop-toolbar-button ${terminalOpen ? 'bg-ops-text/10 text-ops-text' : ''}`}
            onClick={onToggleTerminal}
            aria-pressed={terminalOpen}
            title="打开或关闭当前任务的关联终端（Ctrl/Cmd + J）"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="1.5" /><path d="m7 9 3 3-3 3M13 15h4" /></svg>
            {terminalOpen ? '关闭终端' : '打开终端'}
            <kbd className="desktop-kbd">⌘J</kbd>
          </button>
          <button
            type="button"
            className="desktop-toolbar-button"
            onClick={onCreateConversation}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            新建任务
          </button>
        </div>
      </header>

      <div className="min-h-0 flex flex-1 overflow-hidden">
        <div className="min-w-0 flex flex-1 flex-col overflow-hidden bg-ops-bg relative">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgb(var(--ops-text)/0.012)_1px,transparent_1px)] bg-[size:32px_32px]" />
          {loadError ? (
            <div className="mx-4 mt-4 rounded-md border border-ops-danger/40 bg-ops-danger/10 px-3 py-2 text-sm text-ops-text" role="alert">
              {loadError}
            </div>
          ) : null}

          {backgroundRuns.length > 0 ? (
            <div className="relative z-10 mx-3 mt-3 space-y-1.5" aria-label="后台运行队列">
              {backgroundRuns.slice(0, 3).map((run) => {
                const info = backgroundRunCopy(run)
                return (
                  <div key={run.conversationId} className={`flex items-center gap-3 rounded-md border-l-2 border-y border-r px-3 py-2 text-[11px] font-semibold ${info.tone === 'warning' ? 'border-ops-warning/35 bg-ops-warning/8 text-ops-warning' : info.tone === 'danger' ? 'border-ops-danger/35 bg-ops-danger/8 text-ops-danger' : info.tone === 'success' ? 'border-ops-emerald/30 bg-ops-emerald/8 text-ops-emerald' : 'border-ops-cyan/30 bg-ops-cyan/8 text-ops-cyan'}`}>
                    <span className="min-w-0 flex-1 truncate">{info.message} · {run.assetName}</span>
                    {run.hasUnread ? <span className="rounded-full bg-current/10 px-2 py-0.5 text-[10px]">有新输出</span> : null}
                    <button type="button" className="shrink-0 rounded-xl border border-current/30 px-3 py-1.5 text-[10px] font-black transition hover:bg-current/10 active:scale-95" onClick={() => onViewBackgroundRun(run.conversationId)}>{info.action}</button>
                  </div>
                )
              })}
              {backgroundRuns.length > 3 ? <div className="px-2 text-[10px] text-ops-muted">另有 {backgroundRuns.length - 3} 个后台任务</div> : null}
            </div>
          ) : null}

          {activeRuntimeSnapshot ? <TaskStatePanel runtime={activeRuntimeSnapshot} /> : null}
          {activeRuntimeSnapshot ? <ExecutionPlan runtime={activeRuntimeSnapshot} runtimeCount={runtimeSummaries.length} /> : null}

          <ConversationView
            events={events}
            hasMoreBefore={eventWindow?.hasMoreBefore ?? false}
            isLoadingOlder={isLoadingOlderEvents}
            pendingApprovalRuntimeId={pendingApprovalRuntimeId}
            onLoadOlder={onLoadOlderEvents}
            onApprove={onApprove}
            onReject={onReject}
            onTerminalRequestDecision={onTerminalRequestDecision}
            onEditRun={onEditRun}
            onRetryRun={onRetryRun}
            actionsDisabled={isRunActive}
          />

          <PromptInput
            prompt={prompt}
            models={models}
            selectedModel={selectedModel}
            selectedAsset={selectedAsset}
            contextStatus={contextStatus}
            blockedRun={null}
            onPromptChange={onPromptChange}
            onModelChange={onModelChange}
            onRun={onRun}
            runStatus={activeRunStatus}
            isRunning={isRunActive}
            onCancel={onCancelRun}
          />
        </div>
      </div>
    </section>
  )
}
