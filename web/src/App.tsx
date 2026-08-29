import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { getStoredTaskTerminalLayout, getStoredTerminalOpen } from './appLayoutState'
import { AssetModals, type AssetModalsRef } from './components/assets/AssetModals'
import { AssetSidebar } from './components/assets/AssetSidebar'
import { AssistantPanel } from './components/assistant/AssistantPanel'
import { ManagementWorkspacePanel, type ManagementWorkspace } from './components/management/ManagementWorkspacePanel'
import { ActivityRail, type PrimaryWorkspace, type WorkspaceSection } from './components/layout/ActivityRail'
import { LoadingState } from './components/layout/LoadingState'
import { ConsolePlaceholder } from './components/layout/ConsolePlaceholder'
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
    rewriteConversation,
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
    busyCommand,
  } = useConsolePageState({ events })

  const {
    pendingApprovalRuntimeId,
    conversationSaveStatus,
    runs,
    backgroundRuns,
    clearRunUnread,
    activeRunStatus,
    isRunActive,
    runAgent,
    cancelRun,
    approveRun,
    rejectRun,
    decideTerminalAccess,
  } = useAgentRun({
    conversationSummaries,
    activeConversationId,
    activeConversationTitle,
    activeConversationIdRef,
    events,
    setEvents,
    createConversation,
    loadConversation,
    upsertConversationSummary,
    refreshConversationList,
    syncConversationRuntimes,
    selectedAsset,
    activeTerminalTab,
    selectedModel,
    setLoadError,
    setContextStatus,
  })

  const knowledgeBase = useKnowledgeBase()

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
          const loadedConversation = await loadConversation(latestConversation.id)
          if (loadedConversation.assetId !== null) selectAsset(loadedConversation.assetId)

          if (!active) {
            return
          }

          setIsConsoleInitialized(true)
          return
        }

        await createConversation(selectedAsset?.id ?? 0)

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
    selectAsset,
    selectedAsset?.id,
    setLoadError,
    t,
  ])

  const renderAssistantPanel = () => {
    if (!selectedAsset) return null
    const activeConversation = conversationSummaries.find((item) => item.id === activeConversationId)
    return (
      <AssistantPanel
        conversationSummaries={conversationSummaries}
        activeConversationId={activeConversationId}
        activeConversationTitle={activeConversationTitle}
        conversationScopeMode={activeConversation?.scopeMode ?? 'single'}
        allowedAssetCount={activeConversation?.allowedAssetIds.length ?? 1}
        backgroundRuns={backgroundRuns}
        events={events}
        eventWindow={eventWindow}
        isLoadingOlderEvents={isLoadingOlderEvents}
        pendingApprovalRuntimeId={pendingApprovalRuntimeId}
        runtimeSummaries={runtimeSummaries}
        activeRuntimeSnapshot={activeRuntimeSnapshot}
        models={bootstrap.modelOptions}
        selectedModel={selectedModel}
        prompt={prompt}
        selectedAsset={selectedAsset}
        contextStatus={contextStatus}
        loadError={loadError}
        conversationSaveStatus={conversationSaveStatus}
        terminalOpen={terminalOpen}
        onToggleTerminal={() => {
          setTerminalFocused(false)
          setTerminalOpen((current) => !current)
        }}
        onModelChange={setSelectedModel}
        onPromptChange={setPrompt}
        onViewBackgroundRun={(conversationId) => {
          void loadConversation(conversationId).then((conversation) => {
            if (conversation.assetId !== null) selectAsset(conversation.assetId)
            clearRunUnread(conversationId)
          })
        }}
        onCreateConversation={() => void createConversation(selectedAsset.id, 'single')}
        onCreateMultiAssetConversation={() => void createConversation(selectedAsset.id, 'multi')}
        onSelectConversation={(conversationId) => {
          void loadConversation(conversationId).then((conversation) => {
            if (conversation.assetId !== null) selectAsset(conversation.assetId)
            clearRunUnread(conversationId)
          })
        }}
        onDeleteConversation={(conversationId) => void deleteConversation(conversationId, selectedAsset.id)}
        onRun={(nextPrompt, selectedSkillName, mode) => runAgent(nextPrompt, selectedSkillName, mode)}
        activeRunStatus={activeRunStatus}
        isRunActive={isRunActive}
        onCancelRun={cancelRun}
        onApprove={(allowPrefix, guidance) => void approveRun(allowPrefix, guidance)}
        onReject={(guidance) => void rejectRun(guidance)}
        onTerminalRequestDecision={decideTerminalAccess}
        onLoadOlderEvents={loadOlderConversationEvents}
        onEditRun={async (eventId, nextPrompt) => {
          if (!activeConversationId || isRunActive) return
          setLoadError(null)
          try {
            await rewriteConversation(activeConversationId, eventId)
            await runAgent(nextPrompt)
          } catch (error) {
            setLoadError(error instanceof Error ? error.message : '编辑并重新发送失败。')
          }
        }}
        onRetryRun={async (eventId, nextPrompt) => {
          if (!activeConversationId || isRunActive) return
          setLoadError(null)
          try {
            await rewriteConversation(activeConversationId, eventId)
            await runAgent(nextPrompt)
          } catch (error) {
            setLoadError(error instanceof Error ? error.message : '重试失败。')
          }
        }}
        onExtractKnowledge={async () => {
          if (!activeConversationId || isRunActive) return
          knowledgeBase.clearDraft()
          setManagementWorkspace('knowledge')
          setSidebarCollapsed(true)
          await knowledgeBase.generateDraft(activeConversationId, { modelName: selectedModel || null })
        }}
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
          void loadConversation(conversationId).then((conversation) => {
            if (conversation.assetId !== null) selectAsset(conversation.assetId)
          })
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
          runs={runs}
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
            void loadConversation(conversationId).then((conversation) => {
              if (conversation.assetId !== null) selectAsset(conversation.assetId)
            })
          }}
          onDeleteConversation={(conversationId, cancelActive) => {
            setLoadError(null)
            void deleteConversation(conversationId, selectedAssetId, cancelActive).catch((error: unknown) => {
              setLoadError(error instanceof Error ? error.message : '删除会话失败。')
            })
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
            <ManagementWorkspacePanel
              workspace={managementWorkspace}
              loadingMessage={t('settings.loading')}
              assets={bootstrap.assets}
              groups={bootstrap.groups}
              sshKeys={bootstrap.sshKeys}
              conversationId={activeConversationId}
              conversationTitle={activeConversationTitle}
              selectedModel={selectedModel}
              contextStatus={contextStatus}
              knowledge={knowledgeBase}
              onGroupsChange={replaceGroups}
              onSSHKeysChange={replaceSSHKeys}
            />
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
          ) : <ConsolePlaceholder error={loadError} emptyMessage={t('app.awaitingTargetSelection')} />}
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
