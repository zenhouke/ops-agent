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

type BackgroundRunStatus = 'running' | 'needs_approval' | 'completed' | 'failed'

type BackgroundRunState = {
  conversationId: string
  title: string
  status: BackgroundRunStatus
  hasUnread: boolean
}

type AssistantPanelProps = {
  conversationSummaries: ConversationSummary[]
  activeConversationId: string | null
  activeConversationTitle: string
  backgroundRun: BackgroundRunState | null
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
  terminalOpen: boolean
  onToggleTerminal: () => void
  onModelChange: (model: string) => void
  onPromptChange: (prompt: string) => void
  onViewBackgroundRun: (conversationId: string) => void
  onCreateConversation: () => void
  onSelectConversation: (conversationId: string) => void
  onDeleteConversation: (conversationId: string) => void
  onRun: (prompt: string, selectedSkillName?: string | null) => Promise<void>
  isRunActive: boolean
  onCancelRun: () => Promise<void>
  onApprove: (allowPrefix?: string) => void
  onReject: () => void
  onTerminalRequestDecision?: (input: { runtimeId: string; requestId: string; approvalToken: string; approved: boolean }) => Promise<void>
  onLoadOlderEvents: () => Promise<void>
}

function backgroundRunCopy(run: BackgroundRunState) {
  if (run.status === 'needs_approval') {
    return { message: `会话「${run.title}」需要审批`, action: '前往处理', tone: 'warning' as const }
  }
  if (run.status === 'completed') {
    return { message: `会话「${run.title}」已完成`, action: '查看', tone: 'success' as const }
  }
  if (run.status === 'failed') {
    return { message: `会话「${run.title}」执行失败`, action: '查看', tone: 'danger' as const }
  }
  return { message: `会话「${run.title}」正在后台运行`, action: '查看', tone: 'running' as const }
}

export function AssistantPanel({
  activeConversationTitle,
  backgroundRun,
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
  terminalOpen,
  onToggleTerminal,
  onModelChange,
  onPromptChange,
  onViewBackgroundRun,
  onCreateConversation,
  onSelectConversation,
  onDeleteConversation,
  onRun,
  isRunActive,
  onCancelRun,
  onApprove,
  onReject,
  onTerminalRequestDecision,
  onLoadOlderEvents,
}: AssistantPanelProps) {
  const { t } = useAppearance()
  const backgroundRunInfo = backgroundRun ? backgroundRunCopy(backgroundRun) : null

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
          <span className="hidden items-center gap-1.5 text-[9px] text-ops-muted/60 lg:inline-flex"><span className="h-1.5 w-1.5 rounded-full bg-ops-green" />任务工作台</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
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

          {backgroundRun && backgroundRunInfo ? (
            <div className={`relative z-10 mx-3 mt-3 flex items-center gap-3 rounded-md border-l-2 border-y border-r px-3 py-2 text-[11px] font-semibold ${backgroundRunInfo.tone === 'warning' ? 'border-ops-warning/35 bg-ops-warning/8 text-ops-warning' : backgroundRunInfo.tone === 'danger' ? 'border-ops-danger/35 bg-ops-danger/8 text-ops-danger' : backgroundRunInfo.tone === 'success' ? 'border-ops-emerald/30 bg-ops-emerald/8 text-ops-emerald' : 'border-ops-cyan/30 bg-ops-cyan/8 text-ops-cyan'}`}>
              <span className="min-w-0 flex-1 truncate">{backgroundRunInfo.message}</span>
              {backgroundRun.hasUnread ? <span className="rounded-full bg-current/10 px-2 py-0.5 text-[10px]">有新输出</span> : null}
              <button
                type="button"
                className="shrink-0 rounded-xl border border-current/30 px-3 py-1.5 text-[10px] font-black transition hover:bg-current/10 active:scale-95"
                onClick={() => onViewBackgroundRun(backgroundRun.conversationId)}
              >
                {backgroundRunInfo.action}
              </button>
            </div>
          ) : null}

          <ConversationView
            events={events}
            runtimeSummaries={runtimeSummaries}
            targetLabel={selectedAsset.host || selectedAsset.name}
            targetMeta={selectedAsset.host ? undefined : '本地终端'}
            hasMoreBefore={eventWindow?.hasMoreBefore ?? false}
            isLoadingOlder={isLoadingOlderEvents}
            pendingApprovalRuntimeId={pendingApprovalRuntimeId}
            onLoadOlder={onLoadOlderEvents}
            onApprove={onApprove}
            onReject={onReject}
            onTerminalRequestDecision={onTerminalRequestDecision}
            onSelectSuggestion={(suggestion) => {
              onPromptChange(suggestion)
              requestAnimationFrame(() => document.getElementById('prompt-input')?.focus())
            }}
          />

          <PromptInput
            prompt={prompt}
            models={models}
            selectedModel={selectedModel}
            selectedAsset={selectedAsset}
            contextStatus={contextStatus}
            blockedRun={backgroundRun && (backgroundRun.status === 'running' || backgroundRun.status === 'needs_approval') ? { message: '另一个会话正在运行，当前暂不支持并行执行', actionLabel: backgroundRun.status === 'needs_approval' ? '前往处理' : '查看运行会话' } : null}
            onViewBlockedRun={backgroundRun ? () => onViewBackgroundRun(backgroundRun.conversationId) : undefined}
            onPromptChange={onPromptChange}
            onModelChange={onModelChange}
            onRun={onRun}
            isRunning={isRunActive}
            onCancel={onCancelRun}
          />
        </div>
      </div>
    </section>
  )
}
