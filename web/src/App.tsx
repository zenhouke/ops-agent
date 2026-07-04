import { useEffect, useRef, useState } from 'react'
import { AssetModals, type AssetModalsRef } from './components/assets/AssetModals'
import { ExplorerSidebar } from './components/assets/ExplorerSidebar'
import { AssistantPanel } from './components/assistant/AssistantPanel'
import { KnowledgeDrawer } from './components/knowledge/KnowledgeDrawer'
import { LoadingState } from './components/layout/LoadingState'
import { StatusBar } from './components/layout/StatusBar'
import { TopBar } from './components/layout/TopBar'
import { SettingsDialog } from './components/settings/SettingsDialog'
import { TerminalSidePanel } from './components/terminal/TerminalSidePanel'
import { useAgentRun } from './hooks/console/useAgentRun'
import { useAssetCatalog } from './hooks/console/useAssetCatalog'
import { useConsoleBootstrap } from './hooks/console/useConsoleBootstrap'
import { useConversationState } from './hooks/console/useConversationState'
import { useConsolePageState } from './hooks/console/useConsolePageState'
import { useOrchestrationRun } from './hooks/console/useOrchestrationRun'
import { useTerminalSessions } from './hooks/console/useTerminalSessions'
import { useAppearance } from './hooks/useAppearance'
import { useKnowledgeBase } from './hooks/useKnowledgeBase'

function shouldUseOrchestration(prompt: string) {
  const normalized = prompt.toLowerCase()
  return (
    normalized.includes('多资产')
    || normalized.includes('多个资产')
    || normalized.includes('批量')
    || normalized.includes('每台')
    || normalized.includes('所有资产')
    || normalized.includes('全部资产')
    || normalized.includes('所有网络设备')
    || normalized.includes('全部网络设备')
    || normalized.includes('所有交换机')
    || normalized.includes('全部交换机')
    || normalized.includes('所有 linux')
    || normalized.includes('全部 linux')
    || normalized.includes('所有linux')
    || normalized.includes('全部linux')
    || normalized.includes('all assets')
    || normalized.includes('every asset')
    || normalized.includes('multiple assets')
    || normalized.includes('multi-asset')
  )
}

export function App() {
  const { t } = useAppearance()
  const assetModalsRef = useRef<AssetModalsRef>(null)

  const {
    bootstrap,
    isBootstrapLoaded,
    setBootstrap,
    selectedModel,
    setSelectedModel,
    prompt,
    setPrompt,
    loadError,
    setLoadError,
  } = useConsoleBootstrap()

  const {
    conversationSummaries,
    activeConversationId,
    activeConversationIdRef,
    activeConversationTitle,
    events,
    eventWindow,
    isLoadingOlderEvents,
    setEvents,
    runtimeSummaries,
    activeRuntimeSnapshot,
    contextStatus,
    setContextStatus,
    loadConversation,
    loadOlderConversationEvents,
    syncConversationRuntimes,
    refreshConversationList,
    createConversation,
    deleteConversation,
    upsertConversationSummary,
  } = useConversationState(selectedModel)

  const {
    terminalTabs,
    activeTerminalAssetId,
    setActiveTerminalAssetId,
    selectedAsset,
    activeTerminalTab,
    removeTerminalTab,
    sendTerminalInput,
    resizeTerminal,
    initializeLocalTerminal,
    selectAsset,
    clearActiveTerminal,
    copyActiveTerminalOutput,
    reconnectActiveTerminal,
  } = useTerminalSessions({
    assets: bootstrap.assets,
    historyByAsset: bootstrap.historyByAsset,
    setLoadError,
  })

  const {
    addAsset,
    updateAsset,
    deleteAsset,
    replaceGroups,
    replaceModelOptions,
    replaceSSHKeys,
  } = useAssetCatalog({
    bootstrap,
    setBootstrap,
    selectAsset,
    removeTerminalTab,
    setSelectedModel,
  })

  const terminalOutput = activeTerminalTab?.output ?? ''
  const selectedAssetId = selectedAsset?.id ?? 0
  const [isConsoleInitialized, setIsConsoleInitialized] = useState(false)
  const [knowledgeDrawerOpen, setKnowledgeDrawerOpen] = useState(false)
  const {
    activeModal,
    setActiveModal,
    sidebarCollapsed,
    setSidebarCollapsed,
    assetsDrawerOpen,
    setAssetsDrawerOpen,
    terminalDrawerOpen,
    setTerminalDrawerOpen,
    runMode,
    setRunMode,
    busyCommand,
  } = useConsolePageState({ events, activeRuntimeSnapshot })

  const {
    pendingApprovalRuntimeId,
    backgroundRun,
    activeBackgroundRun,
    clearBackgroundRunUnread,
    runAgent,
    approveRun,
    rejectRun,
    approvePlanRun,
    decideTerminalAccess,
  } = useAgentRun({
    activeConversationId,
    activeConversationTitle,
    activeConversationIdRef,
    events,
    setEvents,
    createConversation,
    upsertConversationSummary,
    refreshConversationList,
    syncConversationRuntimes,
    runtimeSummaries,
    selectedAsset,
    activeTerminalTab,
    selectedModel,
    runMode,
    setLoadError,
    setContextStatus,
  })

  const orchestration = useOrchestrationRun()

  useEffect(() => {
    void orchestration.restoreFromConversation(activeConversationId, events)
  }, [activeConversationId, events, orchestration.restoreFromConversation])

  const {
    entries: knowledgeEntries,
    total: knowledgeTotal,
    limit: knowledgeLimit,
    offset: knowledgeOffset,
    loading: knowledgeLoading,
    error: knowledgeError,
    draft: knowledgeDraft,
    draftSourceConversation: knowledgeDraftSourceConversation,
    draftLoading: knowledgeDraftLoading,
    draftError: knowledgeDraftError,
    saving: knowledgeSaving,
    reindexing: knowledgeReindexing,
    search: searchKnowledge,
    generateDraft: generateKnowledgeDraft,
    clearDraft: clearKnowledgeDraft,
    saveDraft: saveKnowledgeDraft,
    deleteEntry: deleteKnowledgeEntry,
    reindex: reindexKnowledge,
    setDraft: setKnowledgeDraft,
  } = useKnowledgeBase()

  useEffect(() => {
    if (!isBootstrapLoaded || loadError || isConsoleInitialized) {
      return
    }

    let active = true

    void (async () => {
      try {
        initializeLocalTerminal(
          bootstrap.terminalSessionId,
          bootstrap.terminalOutput,
          bootstrap.terminalSessionError
        )

        const items = await refreshConversationList()
        if (!active) {
          return
        }

        if (items.length > 0) {
          const [latestConversation] = [...items].sort((left, right) =>
            right.updatedAt.localeCompare(left.updatedAt)
          )
          await loadConversation(latestConversation.id)

          if (!active) {
            return
          }

          setIsConsoleInitialized(true)
          return
        }

        await createConversation()

        if (!active) {
          return
        }

        setIsConsoleInitialized(true)
      } catch (error: unknown) {
        if (!active) {
          return
        }

        setLoadError(
          error instanceof Error
            ? t('app.loadingConversations', { message: error.message })
            : t('app.loadingConversationsFallback')
        )
        setIsConsoleInitialized(false)
      }
    })()

    return () => {
      active = false
    }
  }, [
    bootstrap.terminalOutput,
    bootstrap.terminalSessionError,
    bootstrap.terminalSessionId,
    createConversation,
    initializeLocalTerminal,
    isBootstrapLoaded,
    isConsoleInitialized,
    loadConversation,
    loadError,
    refreshConversationList,
    setLoadError,
    t,
  ])

  if (loadError && bootstrap.assets.length === 0) {
    return <LoadingState message={loadError} />
  }

  const activeOrchestrationApprovalRuntimeId = orchestration.pendingApprovals[0]?.runtimeId ?? null
  const pendingRuntimeBelongsToOrchestration = Boolean(
    pendingApprovalRuntimeId &&
    orchestration.snapshot?.children.some((child) => child.runtimeId === pendingApprovalRuntimeId)
  )
  const activePendingApprovalRuntimeId = activeOrchestrationApprovalRuntimeId ?? (pendingRuntimeBelongsToOrchestration ? null : pendingApprovalRuntimeId)
  const findOrchestrationApproval = (input: { runtimeId: string | null; approvalToken: string | null }) => {
    if (!input.runtimeId) {
      return null
    }
    return orchestration.pendingApprovals.find((approval) => (
      approval.runtimeId === input.runtimeId &&
      (!input.approvalToken || approval.approvalToken === input.approvalToken)
    )) ?? null
  }

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-ops-bg text-ops-text">
      {/* 动态极光背景：两团缓慢漂移的光晕，让页面"活"起来 */}
      <div className="aurora-bg" />
      <TopBar
        onOpenSettings={() => setActiveModal('settings')}
        onOpenKnowledge={() => setKnowledgeDrawerOpen(true)}
        onToggleAssets={() => setAssetsDrawerOpen((prev) => !prev)}
        onToggleTerminal={() => setTerminalDrawerOpen((prev) => !prev)}
        assetsOpen={assetsDrawerOpen}
        terminalOpen={terminalDrawerOpen}
        terminalCount={terminalTabs.length}
        assets={bootstrap.assets}
        onSelectConversation={(conversationId) => {
          void loadConversation(conversationId)
        }}
        onSelectAsset={selectAsset}
      />

      <main className="flex flex-1 overflow-hidden">
        <ExplorerSidebar
          open={assetsDrawerOpen}
          onClose={() => setAssetsDrawerOpen(false)}
          assets={bootstrap.assets}
          groups={bootstrap.groups}
          selectedAssetId={selectedAssetId}
          onSelectAsset={selectAsset}
          onUpdateAsset={updateAsset}
          onDeleteAsset={deleteAsset}
          onAddAsset={() => assetModalsRef.current?.openAddModal()}
          onEditAsset={(asset) => assetModalsRef.current?.openEditModal(asset)}
          onDeleteAssetConfirm={(asset) => assetModalsRef.current?.openDeleteModal(asset)}
        />

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Assistant panel — full width */}
          <div className="flex-1 overflow-hidden">
            {selectedAsset ? (
              <AssistantPanel
                conversationSummaries={conversationSummaries}
                activeConversationId={activeConversationId}
                activeConversationTitle={activeConversationTitle}
                backgroundRun={activeBackgroundRun}
                events={events}
                eventWindow={eventWindow}
                isLoadingOlderEvents={isLoadingOlderEvents}
                pendingApprovalRuntimeId={activePendingApprovalRuntimeId}
                orchestrationSnapshot={orchestration.snapshot}
                orchestrationTargetPreview={orchestration.targetPreview}
                orchestrationResolvingTargets={orchestration.resolvingTargets}
                orchestrationRunning={orchestration.running}
                runtimeSummaries={runtimeSummaries}
                activeRuntimeSnapshot={activeRuntimeSnapshot}
                models={bootstrap.modelOptions}
                selectedModel={selectedModel}
                prompt={prompt}
                runMode={runMode}
                selectedAsset={selectedAsset}
                contextStatus={contextStatus}
                loadError={loadError}
                onModelChange={setSelectedModel}
                onRunModeChange={setRunMode}
                onPromptChange={setPrompt}
                onViewBackgroundRun={(conversationId) => {
                  void loadConversation(conversationId).then(() => {
                    clearBackgroundRunUnread(conversationId)
                  })
                }}
                onCreateConversation={() => {
                  void createConversation()
                }}
                onSelectConversation={(conversationId) => {
                  void loadConversation(conversationId).then(() => {
                    clearBackgroundRunUnread(conversationId)
                  })
                }}
                onDeleteConversation={(conversationId) => {
                  void deleteConversation(conversationId)
                }}
                onRun={(nextPrompt, selectedSkillName) => {
                  if (runMode === 'agent' && activeConversationId && shouldUseOrchestration(nextPrompt)) {
                    return orchestration.resolveTargets({
                      prompt: nextPrompt,
                      currentAsset: selectedAsset,
                      assets: bootstrap.assets,
                      conversationId: activeConversationId,
                      modelName: selectedModel,
                      selectedSkillName,
                      maxConcurrency: 3,
                    })
                  }
                  return runAgent(nextPrompt, selectedSkillName)
                }}
                onConfirmOrchestration={() => {
                  void orchestration.confirmAndRun()
                }}
                onCancelOrchestrationPreview={orchestration.clearTargetPreview}
                onCancelOrchestration={() => {
                  void orchestration.cancel()
                }}
                onApproveOrchestrationChild={(runtimeId, approvalToken, allowPrefix) => {
                  void orchestration.approveChildRun(runtimeId, approvalToken, allowPrefix)
                }}
                onRejectOrchestrationChild={(runtimeId, approvalToken) => {
                  void orchestration.rejectChildRun(runtimeId, approvalToken)
                }}
                onApprove={(allowPrefix) => {
                  void approveRun(allowPrefix)
                }}
                onReject={() => {
                  void rejectRun()
                }}
                onApproveCommand={(input) => {
                  const orchestrationApproval = findOrchestrationApproval(input)
                  if (orchestrationApproval) {
                    void orchestration.approveChildRun(orchestrationApproval.runtimeId, orchestrationApproval.approvalToken, input.allowPrefix)
                    return
                  }
                  void approveRun(input.allowPrefix, input.terminalId)
                }}
                onRejectCommand={(input) => {
                  const orchestrationApproval = findOrchestrationApproval(input)
                  if (orchestrationApproval) {
                    void orchestration.rejectChildRun(orchestrationApproval.runtimeId, orchestrationApproval.approvalToken)
                    return
                  }
                  void rejectRun(input.terminalId)
                }}
                onApprovePlan={(runtimeId) => {
                  void approvePlanRun(runtimeId)
                }}
                onTerminalRequestDecision={decideTerminalAccess}
                onLoadOlderEvents={loadOlderConversationEvents}
                onOpenSettings={() => setActiveModal('settings')}
              />
            ) : loadError ? (
              <section className="flex h-full items-center justify-center border-x border-ops-border/40 bg-ops-deep">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgb(var(--ops-danger)/0.05),transparent_80%)] pointer-events-none" />
                <p className="text-ops-danger font-bold tracking-[0.1em] text-[11px] shadow-glow">{loadError}</p>
              </section>
            ) : (
              <section className="flex h-full items-center justify-center border-x border-ops-border/40 bg-ops-deep">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgb(var(--ops-green)/0.04),transparent_80%)] pointer-events-none" />
                <div className="flex flex-col items-center gap-4">
                  <div className="h-12 w-12 rounded-2xl border border-ops-green/20 bg-ops-panel/40 flex items-center justify-center text-ops-muted/60 animate-glow-pulse">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
                  </div>
                  <p className="text-ops-muted/70 font-bold tracking-[0.1em] text-[10px]">{t('app.awaitingTargetSelection')}</p>
                </div>
              </section>
            )}
          </div>

          {/* Status bar */}
          <StatusBar
            selectedAsset={selectedAsset}
            terminalOpen={false}
            terminalCount={terminalTabs.length}
            busyCommand={busyCommand}
            backgroundRun={backgroundRun}
            selectedModel={selectedModel}
          />
        </div>

        {/* Terminal drawer — right side */}
        <TerminalSidePanel
          open={terminalDrawerOpen}
          onClose={() => setTerminalDrawerOpen(false)}
          terminalTabs={terminalTabs}
          activeAssetId={activeTerminalAssetId}
          busyCommand={busyCommand}
          onSelectTab={setActiveTerminalAssetId}
          onCloseTab={removeTerminalTab}
          onInput={sendTerminalInput}
          onResize={resizeTerminal}
          onClear={clearActiveTerminal}
          onCopy={() => {
            void copyActiveTerminalOutput()
          }}
          onReconnect={() => {
            void reconnectActiveTerminal()
          }}
        />
      </main>

      <AssetModals
        ref={assetModalsRef}
        assets={bootstrap.assets}
        groups={bootstrap.groups}
        sshKeys={bootstrap.sshKeys}
        onAddAsset={addAsset}
        onUpdateAsset={async (id, payload) => {
          await updateAsset(id, payload)
        }}
        onDeleteAsset={deleteAsset}
      />

      <KnowledgeDrawer
        open={knowledgeDrawerOpen}
        conversationId={activeConversationId}
        selectedModel={selectedModel}
        draft={knowledgeDraft}
        draftSourceConversation={knowledgeDraftSourceConversation}
        draftLoading={knowledgeDraftLoading}
        draftError={knowledgeDraftError}
        saving={knowledgeSaving}
        entries={knowledgeEntries}
        total={knowledgeTotal}
        limit={knowledgeLimit}
        offset={knowledgeOffset}
        loading={knowledgeLoading}
        error={knowledgeError}
        reindexing={knowledgeReindexing}
        knowledgeEntriesInjected={contextStatus?.knowledgeEntriesInjected}
        knowledgeContextChars={contextStatus?.knowledgeContextChars}
        onClose={() => setKnowledgeDrawerOpen(false)}
        onSearch={searchKnowledge}
        onDeleteEntry={deleteKnowledgeEntry}
        onReindex={reindexKnowledge}
        onGenerateDraft={generateKnowledgeDraft}
        onSaveDraft={saveKnowledgeDraft}
        onClearDraft={clearKnowledgeDraft}
        onDraftChange={setKnowledgeDraft}
      />

      {activeModal === 'settings' ? (
        <SettingsDialog
          initialGroups={bootstrap.groups}
          sshKeys={bootstrap.sshKeys}
          assets={bootstrap.assets}
          selectedModel={selectedModel}
          onSelectedModelChange={setSelectedModel}
          onGroupsChange={replaceGroups}
          onModelOptionsChange={replaceModelOptions}
          onSSHKeysChange={replaceSSHKeys}
          onClose={() => setActiveModal(null)}
        />
      ) : null}
    </div>
  )
}
