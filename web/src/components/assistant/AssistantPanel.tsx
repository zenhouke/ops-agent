import type { RunMode } from '../../types/api'
import type {
  Asset,
  ConversationContextStatus,
  ConversationSummary,
  EventItem,
  OrchestrationSnapshot,
  RuntimeSnapshot,
  RuntimeSummary,
} from '../../types/ops'
import { ConversationHistoryDropdown } from './ConversationHistoryDropdown'
import { ConversationView } from './ConversationView'
import { OrchestrationCard } from './conversation/OrchestrationCard'
import { OrchestrationTargetConfirmCard } from './conversation/OrchestrationTargetConfirmCard'
import { PromptInput } from './PromptInput'
import { useAppearance } from '../../hooks/useAppearance'
import type { TranslationKey } from '../../i18n/translations'
import type { OrchestrationTargetPreview } from '../../hooks/console/useOrchestrationRun'
import type { ConversationRunBadge } from './ConversationList'

type BackgroundRunStatus = 'running' | 'needs_approval' | 'completed' | 'failed'

type BackgroundRunState = {
  conversationId: string
  title: string
  status: BackgroundRunStatus
  hasUnread: boolean
} & ConversationRunBadge

type AssistantPanelProps = {
  conversationSummaries: ConversationSummary[]
  activeConversationId: string | null
  activeConversationTitle: string
  backgroundRun: BackgroundRunState | null
  events: EventItem[]
  eventWindow: { hasMoreBefore: boolean } | null
  isLoadingOlderEvents: boolean
  pendingApprovalRuntimeId: string | null
  orchestrationSnapshot: OrchestrationSnapshot | null
  orchestrationTargetPreview: OrchestrationTargetPreview | null
  orchestrationResolvingTargets: boolean
  orchestrationRunning: boolean
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
  onConfirmOrchestration: () => void
  onCancelOrchestrationPreview: () => void
  onCancelOrchestration: () => void
  onApproveOrchestrationChild: (runtimeId: string, approvalToken: string | null, allowPrefix?: string) => void
  onRejectOrchestrationChild: (runtimeId: string, approvalToken: string | null) => void
  onApprove: (allowPrefix?: string) => void
  onReject: () => void
  onApproveCommand: (input: { runtimeId: string | null; approvalToken: string | null; terminalId: string | null; allowPrefix?: string }) => void
  onRejectCommand: (input: { runtimeId: string | null; approvalToken: string | null; terminalId: string | null }) => void
  onApprovePlan?: (runtimeId: string) => void
  onTerminalRequestDecision?: (input: { runtimeId: string; requestId: string; approvalToken: string; approved: boolean }) => Promise<void>
  onLoadOlderEvents: () => Promise<void>
  onOpenSettings?: () => void
}

function backgroundRunCopy(run: BackgroundRunState, t: (key: TranslationKey, values?: Record<string, string>) => string) {
  if (run.status === 'needs_approval') {
    return {
      message: t('assistant.backgroundRunNeedsApproval', { title: run.title }),
      action: t('assistant.backgroundRunActionHandle'),
      tone: 'warning' as const,
      badge: 'bg-ops-warning/10',
      button: 'border-ops-warning/30 hover:bg-ops-warning/10',
    }
  }
  if (run.status === 'completed') {
    return {
      message: t('assistant.backgroundRunCompleted', { title: run.title }),
      action: t('assistant.backgroundRunActionView'),
      tone: 'success' as const,
      badge: 'bg-ops-emerald/10',
      button: 'border-ops-emerald/30 hover:bg-ops-emerald/10',
    }
  }
  if (run.status === 'failed') {
    return {
      message: t('assistant.backgroundRunFailed', { title: run.title }),
      action: t('assistant.backgroundRunActionView'),
      tone: 'danger' as const,
      badge: 'bg-ops-danger/10',
      button: 'border-ops-danger/30 hover:bg-ops-danger/10',
    }
  }
  return {
    message: t('assistant.backgroundRunRunning', { title: run.title }),
    action: t('assistant.backgroundRunActionView'),
    tone: 'running' as const,
    badge: 'bg-ops-green/10',
    button: 'border-ops-green/30 hover:bg-ops-green/10',
  }
}

export function AssistantPanel({
  conversationSummaries,
  activeConversationId,
  activeConversationTitle,
  backgroundRun,
  events,
  eventWindow,
  isLoadingOlderEvents,
  pendingApprovalRuntimeId,
  orchestrationSnapshot,
  orchestrationTargetPreview,
  orchestrationResolvingTargets,
  orchestrationRunning,
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
  onConfirmOrchestration,
  onCancelOrchestrationPreview,
  onCancelOrchestration,
  onApproveOrchestrationChild,
  onRejectOrchestrationChild,
  onApprove,
  onReject,
  onApproveCommand,
  onRejectCommand,
  onApprovePlan,
  onTerminalRequestDecision,
  onLoadOlderEvents,
  onOpenSettings,
}: AssistantPanelProps) {
  const { t } = useAppearance()
  const backgroundRunInfo = backgroundRun ? backgroundRunCopy(backgroundRun, t) : null
  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-ops-bg">
      <header className="relative z-30 flex h-12 shrink-0 items-center justify-between border-b border-ops-border/15 bg-ops-bg/80 backdrop-blur-md px-4 dark:border-ops-border/20 dark:bg-ops-panel/60">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <ConversationHistoryDropdown
            items={conversationSummaries}
            activeConversationId={activeConversationId}
            activeConversationTitle={activeConversationTitle}
            backgroundRun={backgroundRun}
            onSelect={onSelectConversation}
            onDelete={onDeleteConversation}
            onCreate={onCreateConversation}
          />
          {selectedAsset ? (
            <div className="flex shrink-0 items-center gap-1.5 rounded-md border border-ops-green/20 bg-ops-green/10 px-2 py-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-ops-green" />
              <span className="max-w-[120px] truncate text-[10px] font-bold text-ops-green">{selectedAsset.name}</span>
              <span className="text-[9px] text-ops-muted/50 font-mono">{selectedAsset.host || ''}</span>
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-lg border border-ops-green/25 bg-ops-green/10 px-3 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-green transition-all duration-200 hover:bg-ops-green/20 active:scale-95"
            onClick={onCreateConversation}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            {t('assistant.newSession')}
          </button>
        </div>
      </header>

      <div className="min-h-0 flex flex-1 overflow-hidden">
        <div className="min-w-0 flex flex-1 flex-col overflow-hidden bg-ops-bg relative">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgb(var(--ops-green)/0.05),transparent_50%)] pointer-events-none" />
          {loadError ? (
            <div className="mx-4 mt-4 rounded-md border border-ops-danger/40 bg-ops-danger/10 px-3 py-2 text-sm text-ops-text" role="alert">
              {loadError}
            </div>
          ) : null}

          {backgroundRun && backgroundRunInfo ? (
            <div className={`relative z-10 mx-4 mt-4 flex items-center gap-3 rounded-2xl border px-4 py-3 text-xs font-bold ${backgroundRunInfo.tone === 'warning' ? 'border-ops-warning/35 bg-ops-warning/10 text-ops-warning' : backgroundRunInfo.tone === 'danger' ? 'border-ops-danger/35 bg-ops-danger/10 text-ops-danger' : backgroundRunInfo.tone === 'success' ? 'border-ops-emerald/30 bg-ops-emerald/10 text-ops-emerald' : 'border-ops-green/30 bg-ops-green/10 text-ops-green'}`}>
              <span className="min-w-0 flex-1 truncate">{backgroundRunInfo.message}</span>
              {backgroundRun.hasUnread ? <span className={`rounded-full ${backgroundRunInfo.badge} px-2 py-0.5 text-[10px]`}>{t('assistant.backgroundRunUnread')}</span> : null}
              <button
                type="button"
                className={`shrink-0 rounded-xl border ${backgroundRunInfo.button} px-3 py-1.5 text-[10px] font-black transition active:scale-95`}
                onClick={() => onViewBackgroundRun(backgroundRun.conversationId)}
              >
                {backgroundRunInfo.action}
              </button>
            </div>
          ) : null}

          {orchestrationTargetPreview ? (
            <OrchestrationTargetConfirmCard
              prompt={orchestrationTargetPreview.prompt}
              assets={orchestrationTargetPreview.assets}
              preparations={orchestrationTargetPreview.preparations}
              reason={orchestrationTargetPreview.targetSelectionReason}
              confidence={orchestrationTargetPreview.confidence}
              maxConcurrency={orchestrationTargetPreview.maxConcurrency}
              resolving={orchestrationResolvingTargets}
              running={orchestrationRunning}
              onStart={onConfirmOrchestration}
              onCancel={onCancelOrchestrationPreview}
            />
          ) : null}

          {orchestrationSnapshot ? (
            <OrchestrationCard
              snapshot={orchestrationSnapshot}
              onCancel={onCancelOrchestration}
              onApprove={onApproveOrchestrationChild}
              onReject={onRejectOrchestrationChild}
            />
          ) : null}

          <ConversationView
            events={events}
            hasMoreBefore={eventWindow?.hasMoreBefore ?? false}
            isLoadingOlder={isLoadingOlderEvents}
            pendingApprovalRuntimeId={pendingApprovalRuntimeId}
            onLoadOlder={onLoadOlderEvents}
            onApprove={onApprove}
            onReject={onReject}
            onApproveCommand={onApproveCommand}
            onRejectCommand={onRejectCommand}
            onApprovePlan={onApprovePlan}
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
            onOpenSettings={onOpenSettings}
          />
        </div>
      </div>
    </div>
  )
}
