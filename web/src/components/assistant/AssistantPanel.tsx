import type { RunMode } from '../../types/api'
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
  runMode: RunMode
  prompt: string
  selectedAsset: Asset
  contextStatus: ConversationContextStatus | null
  loadError: string | null
  onModelChange: (model: string) => void
  onRunModeChange: (mode: RunMode) => void
  onPromptChange: (prompt: string) => void
  onViewBackgroundRun: (conversationId: string) => void
  onCreateConversation: () => void
  onSelectConversation: (conversationId: string) => void
  onDeleteConversation: (conversationId: string) => void
  onRun: (prompt: string, selectedSkillName?: string | null) => Promise<void>
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
  runMode,
  prompt,
  selectedAsset,
  contextStatus,
  loadError,
  onModelChange,
  onRunModeChange,
  onPromptChange,
  onViewBackgroundRun,
  onCreateConversation,
  onSelectConversation,
  onDeleteConversation,
  onRun,
  onApprove,
  onReject,
  onTerminalRequestDecision,
  onLoadOlderEvents,
}: AssistantPanelProps) {
  const { t } = useAppearance()
  const backgroundRunInfo = backgroundRun ? backgroundRunCopy(backgroundRun) : null

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-ops-bg">
      <header className="relative z-10 flex shrink-0 items-center justify-between border-b border-ops-border/15 bg-ops-deep px-6 py-4 dark:border-ops-border/20 dark:bg-ops-panel/80 dark:shadow-2xl">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[18px] font-black tracking-tight text-ops-text">
            {activeConversationTitle || t('assistant.unclassifiedMission')}
          </h2>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-xl border border-ops-cyan/30 bg-ops-cyan/10 px-4 py-2 text-[10px] font-bold tracking-[0.1em] text-ops-cyan shadow-glow transition-all duration-200 hover:bg-ops-cyan/20 active:scale-95"
            onClick={onCreateConversation}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            {t('assistant.newSession')}
          </button>
        </div>
      </header>

      <div className="min-h-0 flex flex-1 overflow-hidden">
        <div className="min-w-0 flex flex-1 flex-col overflow-hidden bg-ops-bg relative">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(6,182,212,0.05),transparent_50%)] pointer-events-none" />
          {loadError ? (
            <div className="mx-4 mt-4 rounded-md border border-ops-danger/40 bg-ops-danger/10 px-3 py-2 text-sm text-ops-text" role="alert">
              {loadError}
            </div>
          ) : null}

          {backgroundRun && backgroundRunInfo ? (
            <div className={`relative z-10 mx-4 mt-4 flex items-center gap-3 rounded-2xl border px-4 py-3 text-xs font-bold ${backgroundRunInfo.tone === 'warning' ? 'border-ops-warning/35 bg-ops-warning/10 text-ops-warning' : backgroundRunInfo.tone === 'danger' ? 'border-ops-danger/35 bg-ops-danger/10 text-ops-danger' : backgroundRunInfo.tone === 'success' ? 'border-ops-emerald/30 bg-ops-emerald/10 text-ops-emerald' : 'border-ops-cyan/30 bg-ops-cyan/10 text-ops-cyan'}`}>
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
            hasMoreBefore={eventWindow?.hasMoreBefore ?? false}
            isLoadingOlder={isLoadingOlderEvents}
            pendingApprovalRuntimeId={pendingApprovalRuntimeId}
            onLoadOlder={onLoadOlderEvents}
            onApprove={onApprove}
            onReject={onReject}
            onTerminalRequestDecision={onTerminalRequestDecision}
          />

          <PromptInput
            prompt={prompt}
            models={models}
            selectedModel={selectedModel}
            runMode={runMode}
            selectedAsset={selectedAsset}
            contextStatus={contextStatus}
            blockedRun={backgroundRun && (backgroundRun.status === 'running' || backgroundRun.status === 'needs_approval') ? { message: '另一个会话正在运行，当前暂不支持并行执行', actionLabel: backgroundRun.status === 'needs_approval' ? '前往处理' : '查看运行会话' } : null}
            onViewBlockedRun={backgroundRun ? () => onViewBackgroundRun(backgroundRun.conversationId) : undefined}
            onPromptChange={onPromptChange}
            onModelChange={onModelChange}
            onRunModeChange={onRunModeChange}
            onRun={onRun}
          />
        </div>
      </div>
    </div>
  )
}
