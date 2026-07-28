import { useEffect, useRef, useState } from 'react'
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels'
import { AssetModals, type AssetModalsRef } from './components/assets/AssetModals'
import { AssetSidebar } from './components/assets/AssetSidebar'
import { AssistantPanel } from './components/assistant/AssistantPanel'
import { KnowledgeDrawer } from './components/knowledge/KnowledgeDrawer'
import { LoadingState } from './components/layout/LoadingState'
import { TopBar } from './components/layout/TopBar'
import { SettingsDialog } from './components/settings/SettingsDialog'
import { TerminalPanel } from './components/terminal/TerminalPanel'
import { useAgentRun } from './hooks/console/useAgentRun'
import { useAssetCatalog } from './hooks/console/useAssetCatalog'
import { useConsoleBootstrap } from './hooks/console/useConsoleBootstrap'
import { useConversationState } from './hooks/console/useConversationState'
import { useConsolePageState } from './hooks/console/useConsolePageState'
import { useTerminalSessions } from './hooks/console/useTerminalSessions'
import { useAppearance } from './hooks/useAppearance'
import { useKnowledgeBase } from './hooks/useKnowledgeBase'

export function App() {
  const { t } = useAppearance()
  const centerFallbackClassName = 'flex h-full items-center justify-center border-x border-ops-border/40 bg-ops-deep'
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
    runMode,
    setRunMode,
    busyCommand,
  } = useConsolePageState({ events, activeRuntimeSnapshot })

  const {
    pendingApprovalRuntimeId,
    backgroundRun,
    activeBackgroundRun,
    clearBackgroundRunUnread,
    isRunActive,
    runAgent,
    cancelRun,
    approveRun,
    approvePlan,
    rejectRun,
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
    selectedAsset,
    activeTerminalTab,
    selectedModel,
    runMode,
    setLoadError,
    setContextStatus,
  })

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

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[linear-gradient(180deg,rgb(var(--ops-panel))_0,rgb(var(--ops-bg))_92px)] text-ops-text dark:bg-ops-bg">
      <TopBar
        onOpenSettings={() => setActiveModal('settings')}
        onOpenKnowledge={() => setKnowledgeDrawerOpen(true)}
        assets={bootstrap.assets}
        onSelectConversation={(conversationId) => {
          void loadConversation(conversationId)
        }}
        onSelectAsset={selectAsset}
      />

      <main className="flex flex-1 overflow-hidden">
        <AssetSidebar
          assets={bootstrap.assets}
          groups={bootstrap.groups}
          conversationSummaries={conversationSummaries}
          activeConversationId={activeConversationId}
          backgroundRun={backgroundRun}
          selectedAssetId={selectedAssetId}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
          onSelectAsset={selectAsset}
          onSelectConversation={(conversationId) => {
            void loadConversation(conversationId)
          }}
          onDeleteConversation={(conversationId) => {
            void deleteConversation(conversationId)
          }}
          onUpdateAsset={updateAsset}
          onDeleteAsset={deleteAsset}
          onAddAsset={() => assetModalsRef.current?.openAddModal()}
          onEditAsset={(asset) => assetModalsRef.current?.openEditModal(asset)}
          onDeleteAssetConfirm={(asset) => assetModalsRef.current?.openDeleteModal(asset)}
        />

        <PanelGroup orientation="horizontal" className="h-full min-w-0 flex-1">
          <Panel defaultSize={selectedAsset ? 66 : 100} minSize={36}>
            {selectedAsset ? (
              <AssistantPanel
                conversationSummaries={conversationSummaries}
                activeConversationId={activeConversationId}
                activeConversationTitle={activeConversationTitle}
                backgroundRun={activeBackgroundRun}
                events={events}
                eventWindow={eventWindow}
                isLoadingOlderEvents={isLoadingOlderEvents}
                pendingApprovalRuntimeId={pendingApprovalRuntimeId}
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
                  return runAgent(nextPrompt, selectedSkillName)
                }}
                isRunActive={isRunActive}
                onCancelRun={cancelRun}
                onApprove={(allowPrefix) => {
                  void approveRun(allowPrefix)
                }}
                onReject={() => {
                  void rejectRun()
                }}
                onApprovePlan={(runtimeId) => {
                  void approvePlan(runtimeId)
                }}
                onTerminalRequestDecision={decideTerminalAccess}
                onLoadOlderEvents={loadOlderConversationEvents}
              />
            ) : loadError ? (
              <section className={centerFallbackClassName}>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgb(var(--ops-danger)/0.05),transparent_80%)] pointer-events-none" />
                <p className="text-ops-danger font-bold tracking-[0.1em] text-[11px] shadow-glow">{loadError}</p>
              </section>
            ) : (
              <section className={centerFallbackClassName}>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgb(var(--ops-cyan)/0.04),transparent_80%)] pointer-events-none" />
                <div className="flex flex-col items-center gap-4">
                  <div className="h-12 w-12 rounded-2xl border border-ops-border/20 bg-ops-panel/40 flex items-center justify-center text-ops-muted/30">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
                  </div>
                  <p className="text-ops-muted/40 font-bold tracking-[0.1em] text-[10px]">{t('app.awaitingTargetSelection')}</p>
                </div>
              </section>
            )}
          </Panel>

          {selectedAsset ? (
            <>
              <PanelResizeHandle className="w-1.5 bg-transparent group cursor-col-resize flex flex-col items-center justify-center relative z-10">
                <div className="absolute inset-y-0 -left-1 -right-1" />
                <div className="w-px h-full bg-ops-border/10 group-hover:bg-ops-cyan/50 group-active:bg-ops-cyan transition-all duration-300 relative">
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1 h-12 rounded-full bg-ops-border/30 group-hover:bg-ops-cyan shadow-glow" />
                </div>
              </PanelResizeHandle>

              <Panel defaultSize={34} minSize={24}>
                <TerminalPanel
                  asset={selectedAsset}
                  tabs={terminalTabs.map((item) => item.asset)}
                  activeAssetId={activeTerminalAssetId}
                  output={terminalOutput}
                  busyCommand={busyCommand}
                  onInput={sendTerminalInput}
                  onResize={resizeTerminal}
                  onSelectTab={setActiveTerminalAssetId}
                  onCloseTab={removeTerminalTab}
                  onClear={clearActiveTerminal}
                  onCopy={() => {
                    void copyActiveTerminalOutput()
                  }}
                  onReconnect={() => {
                    void reconnectActiveTerminal()
                  }}
                />
              </Panel>
            </>
          ) : null}
        </PanelGroup>
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
