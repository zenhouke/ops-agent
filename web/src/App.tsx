import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Group, Panel, Separator, type Layout } from 'react-resizable-panels'
import { AssetModals, type AssetModalsRef } from './components/assets/AssetModals'
import { AssetSidebar } from './components/assets/AssetSidebar'
import { AssistantPanel } from './components/assistant/AssistantPanel'
import { ActivityRail, type PrimaryWorkspace, type WorkspaceSection } from './components/layout/ActivityRail'
import { LoadingState } from './components/layout/LoadingState'
import { TopBar } from './components/layout/TopBar'
import { StatusBar } from './components/layout/StatusBar'
import { TerminalPanel } from './components/terminal/TerminalPanel'
import { useAgentRun } from './hooks/console/useAgentRun'
import { useAssetCatalog } from './hooks/console/useAssetCatalog'
import { useConsoleBootstrap } from './hooks/console/useConsoleBootstrap'
import { useConversationState } from './hooks/console/useConversationState'
import { useConsolePageState } from './hooks/console/useConsolePageState'
import { useTerminalSessions } from './hooks/console/useTerminalSessions'
import { useAppearance } from './hooks/useAppearance'
import { useKnowledgeBase } from './hooks/useKnowledgeBase'

const SettingsDialog = lazy(() => import('./components/settings/SettingsDialog').then((module) => ({
  default: module.SettingsDialog,
})))
const CredentialsWorkspace = lazy(() => import('./components/management/CredentialsWorkspace').then((module) => ({ default: module.CredentialsWorkspace })))
const AutomationWorkspace = lazy(() => import('./components/management/AutomationWorkspace').then((module) => ({ default: module.AutomationWorkspace })))
const ExtensionsWorkspace = lazy(() => import('./components/management/ExtensionsWorkspace').then((module) => ({ default: module.ExtensionsWorkspace })))
const GroupsWorkspace = lazy(() => import('./components/management/GroupsWorkspace').then((module) => ({ default: module.GroupsWorkspace })))
const KnowledgeWorkspace = lazy(() => import('./components/knowledge/KnowledgeWorkspace').then((module) => ({ default: module.KnowledgeWorkspace })))

type ManagementWorkspace = 'knowledge' | 'credentials' | 'automation' | 'extensions' | 'groups'

const DEFAULT_TASK_TERMINAL_LAYOUT: Layout = { task: 58, terminal: 42 }

function getStoredTerminalOpen() {
  return localStorage.getItem('ops-agent:terminal-open') === 'true'
    || localStorage.getItem('ops-agent:workspace-view') === 'terminal'
}

function getStoredTaskTerminalLayout(): Layout {
  try {
    const value = JSON.parse(localStorage.getItem('ops-agent:task-terminal-layout') ?? '') as Layout
    if (typeof value.task === 'number' && typeof value.terminal === 'number') return value
  } catch {
    // Ignore stale or invalid local layout state.
  }
  return DEFAULT_TASK_TERMINAL_LAYOUT
}

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
  const [terminalOpen, setTerminalOpen] = useState(getStoredTerminalOpen)
  const [terminalFocused, setTerminalFocused] = useState(false)
  const [taskTerminalLayout, setTaskTerminalLayout] = useState(getStoredTaskTerminalLayout)
  const [activeWorkspaceSection, setActiveWorkspaceSection] = useState<WorkspaceSection>('assets')
  const [managementWorkspace, setManagementWorkspace] = useState<ManagementWorkspace | null>(null)
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
    localStorage.setItem('ops-agent:terminal-open', String(terminalOpen))
    localStorage.removeItem('ops-agent:workspace-view')
  }, [terminalOpen])

  useEffect(() => {
    const handleKeyboardShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'j') {
        event.preventDefault()
        if (selectedAsset) {
          if (managementWorkspace) {
            setManagementWorkspace(null)
            setTerminalOpen(true)
            setTerminalFocused(false)
            return
          }
          setTerminalOpen((current) => {
            if (current) setTerminalFocused(false)
            return !current
          })
        }
      } else if (event.key === 'Escape' && terminalFocused) {
        setTerminalFocused(false)
      }
    }
    window.addEventListener('keydown', handleKeyboardShortcut)
    return () => window.removeEventListener('keydown', handleKeyboardShortcut)
  }, [managementWorkspace, selectedAsset, terminalFocused])

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

  const renderAssistantPanel = () => {
    if (!selectedAsset) return null
    return (
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
        terminalOpen={terminalOpen}
        onToggleTerminal={() => {
          setTerminalFocused(false)
          setTerminalOpen((current) => !current)
        }}
        onModelChange={setSelectedModel}
        onRunModeChange={setRunMode}
        onPromptChange={setPrompt}
        onViewBackgroundRun={(conversationId) => {
          void loadConversation(conversationId).then(() => clearBackgroundRunUnread(conversationId))
        }}
        onCreateConversation={() => void createConversation()}
        onSelectConversation={(conversationId) => {
          void loadConversation(conversationId).then(() => clearBackgroundRunUnread(conversationId))
        }}
        onDeleteConversation={(conversationId) => void deleteConversation(conversationId)}
        onRun={(nextPrompt, selectedSkillName) => runAgent(nextPrompt, selectedSkillName)}
        isRunActive={isRunActive}
        onCancelRun={cancelRun}
        onApprove={(allowPrefix) => void approveRun(allowPrefix)}
        onReject={() => void rejectRun()}
        onApprovePlan={(runtimeId) => void approvePlan(runtimeId)}
        onTerminalRequestDecision={decideTerminalAccess}
        onLoadOlderEvents={loadOlderConversationEvents}
      />
    )
  }

  if (loadError && !isBootstrapLoaded) {
    return <LoadingState message={loadError} />
  }

  return (
    <div className="desktop-app-shell">
      <TopBar
        assets={bootstrap.assets}
        selectedAsset={selectedAsset}
        onSelectConversation={(conversationId) => {
          setManagementWorkspace(null)
          setActiveWorkspaceSection('conversations')
          void loadConversation(conversationId)
        }}
        onSelectAsset={(assetId) => {
          setManagementWorkspace(null)
          setActiveWorkspaceSection('assets')
          selectAsset(assetId)
        }}
      />

      <main className="flex min-h-0 flex-1 overflow-hidden">
        <ActivityRail
          activeWorkspace={(managementWorkspace === 'groups' ? 'assets' : managementWorkspace ?? activeWorkspaceSection) as PrimaryWorkspace}
          onSelectWorkspace={(workspace) => {
            if (workspace === 'assets' || workspace === 'conversations') {
              const isCurrentWorkspace = managementWorkspace === null && activeWorkspaceSection === workspace
              setManagementWorkspace(null)
              setActiveWorkspaceSection(workspace)
              setSidebarCollapsed(isCurrentWorkspace ? !sidebarCollapsed : false)
              return
            }
            setManagementWorkspace(workspace)
            setSidebarCollapsed(true)
          }}
          onOpenSettings={() => setActiveModal('settings')}
        />

        {managementWorkspace === null ? <AssetSidebar
          assets={bootstrap.assets}
          groups={bootstrap.groups}
          conversationSummaries={conversationSummaries}
          activeConversationId={activeConversationId}
          backgroundRun={backgroundRun}
          selectedAssetId={selectedAssetId}
          collapsed={sidebarCollapsed}
          activeSection={activeWorkspaceSection}
          onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
          onSelectAsset={(assetId) => {
            setManagementWorkspace(null)
            selectAsset(assetId)
          }}
          onSelectConversation={(conversationId) => {
            setManagementWorkspace(null)
            void loadConversation(conversationId)
          }}
          onDeleteConversation={(conversationId) => {
            void deleteConversation(conversationId)
          }}
          onUpdateAsset={updateAsset}
          onDeleteAsset={deleteAsset}
          onAddAsset={() => assetModalsRef.current?.openAddModal()}
          onManageGroups={() => {
            setManagementWorkspace('groups')
            setSidebarCollapsed(true)
          }}
          onEditAsset={(asset) => assetModalsRef.current?.openEditModal(asset)}
          onDeleteAssetConfirm={(asset) => assetModalsRef.current?.openDeleteModal(asset)}
        /> : null}

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-ops-bg" aria-label="中央工作区">
          {managementWorkspace ? (
            <Suspense fallback={<LoadingState message={t('settings.loading')} />}>
              {managementWorkspace === 'knowledge' ? (
                <KnowledgeWorkspace
                  conversationId={activeConversationId}
                  conversationTitle={activeConversationTitle}
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
                  onSearch={searchKnowledge}
                  onDeleteEntry={deleteKnowledgeEntry}
                  onReindex={reindexKnowledge}
                  onGenerateDraft={generateKnowledgeDraft}
                  onSaveDraft={saveKnowledgeDraft}
                  onClearDraft={clearKnowledgeDraft}
                  onDraftChange={setKnowledgeDraft}
                />
              ) : managementWorkspace === 'credentials' ? (
                <CredentialsWorkspace initialSSHKeys={bootstrap.sshKeys} onSSHKeysChange={replaceSSHKeys} />
              ) : managementWorkspace === 'automation' ? (
                <AutomationWorkspace assets={bootstrap.assets} />
              ) : managementWorkspace === 'extensions' ? (
                <ExtensionsWorkspace />
              ) : (
                <GroupsWorkspace groups={bootstrap.groups} onGroupsChange={replaceGroups} />
              )}
            </Suspense>
          ) : selectedAsset ? (
            terminalFocused && terminalOpen ? (
              <TerminalPanel
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
                focused
                onToggleFocus={() => setTerminalFocused(false)}
                onClose={() => {
                  setTerminalFocused(false)
                  setTerminalOpen(false)
                }}
              />
            ) : terminalOpen ? (
              <Group
                className="h-full min-h-0"
                orientation="horizontal"
                defaultLayout={taskTerminalLayout}
                onLayoutChanged={(layout) => {
                  setTaskTerminalLayout(layout)
                  localStorage.setItem('ops-agent:task-terminal-layout', JSON.stringify(layout))
                }}
              >
                <Panel id="task" minSize="38%" defaultSize="58%">
                  {renderAssistantPanel()}
                </Panel>
                <Separator className="task-terminal-separator" aria-label="调整任务与终端宽度">
                  <span className="task-terminal-separator-grip" aria-hidden="true" />
                </Separator>
                <Panel id="terminal" minSize="32%" defaultSize="42%">
                  <TerminalPanel
                    tabs={terminalTabs.map((item) => item.asset)}
                    activeAssetId={activeTerminalAssetId}
                    output={terminalOutput}
                    busyCommand={busyCommand}
                    onInput={sendTerminalInput}
                    onResize={resizeTerminal}
                    onSelectTab={setActiveTerminalAssetId}
                    onCloseTab={removeTerminalTab}
                    onClear={clearActiveTerminal}
                    onCopy={() => void copyActiveTerminalOutput()}
                    onReconnect={() => void reconnectActiveTerminal()}
                    focused={false}
                    onToggleFocus={() => setTerminalFocused(true)}
                    onClose={() => setTerminalOpen(false)}
                  />
                </Panel>
              </Group>
            ) : (
              renderAssistantPanel()
            )
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
        </section>
      </main>

      <StatusBar
        asset={selectedAsset}
        model={selectedModel}
        contextStatus={contextStatus}
        runtime={activeRuntimeSnapshot}
        terminalCount={terminalTabs.length}
      />

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

      {activeModal === 'settings' ? (
        <Suspense fallback={null}><SettingsDialog
          selectedModel={selectedModel}
          onSelectedModelChange={setSelectedModel}
          onModelOptionsChange={replaceModelOptions}
          onClose={() => setActiveModal(null)}
        /></Suspense>
      ) : null}
    </div>
  )
}
