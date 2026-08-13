import { useState } from 'react'
import { useAppearance } from '../../hooks/useAppearance'
import { useSkillPackages } from '../../hooks/useSkillPackages'
import { DeleteConfirmDialog } from '../settings/DeleteConfirmDialog'
import { McpSection } from '../settings/McpSection'
import { PluginsSection } from '../settings/PluginsSection'
import { SkillsSection } from '../settings/SkillsSection'
import { useMcpSettings } from '../settings/useMcpSettings'
import { ManagementShell } from './ManagementShell'

type ExtensionTab = 'skills' | 'plugins' | 'mcp'

export function ExtensionsWorkspace() {
  const { t } = useAppearance()
  const [activeTab, setActiveTab] = useState<ExtensionTab>('skills')
  const { skillPackages, loading, error, loadSkillPackages } = useSkillPackages()
  const mcp = useMcpSettings()
  const tabs: ExtensionTab[] = ['skills', 'plugins', 'mcp']

  return (
    <ManagementShell
      title={t('management.extensions')}
      description={t('management.extensionsDescription')}
      actions={(
        <nav className="flex items-center rounded-md border border-ops-border/35 bg-ops-bg p-0.5" aria-label={t('management.extensionTypes')}>
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`rounded px-3 py-1.5 text-[10px] font-medium transition-all duration-200 active:scale-95 ${activeTab === tab ? 'bg-ops-text text-ops-bg' : 'text-ops-muted hover:bg-ops-panel hover:text-ops-text'}`}
              onClick={() => setActiveTab(tab)}
            >
              {t(`settings.${tab}`)}
            </button>
          ))}
        </nav>
      )}
    >
      {activeTab === 'skills' ? (
        <SkillsSection skills={skillPackages ?? []} loading={loading} error={error} onRetry={() => void loadSkillPackages(true)} />
      ) : activeTab === 'plugins' ? (
        <PluginsSection />
      ) : (
        <McpSection
          servers={mcp.servers}
          serverForm={mcp.serverForm}
          showServerForm={mcp.showServerForm}
          editingServer={mcp.editingServer}
          selectedServerId={mcp.selectedServerId}
          loading={mcp.loading}
          error={mcp.error}
          saving={mcp.saving}
          testResult={mcp.testResult}
          onRetry={() => void mcp.load()}
          onStartCreate={mcp.startCreate}
          onStartEdit={mcp.startEdit}
          onStartDelete={mcp.setDeletingServer}
          onSelectServer={mcp.setSelectedServerId}
          onFormChange={mcp.setServerForm}
          onCancelForm={mcp.resetForm}
          onSave={mcp.save}
          onTest={(server) => void mcp.test(server)}
          onRefresh={(server) => void mcp.refresh(server)}
          onSetEnabled={(server, enabled) => void mcp.setEnabled(server, enabled)}
          onUpdateTool={(tool, updates) => void mcp.updateTool(tool, updates)}
        />
      )}
      {mcp.deletingServer ? (
        <DeleteConfirmDialog
          titleId="delete-mcp-server-title"
          title={t('settings.confirmMcpServerDeletion')}
          message={mcp.deletingServer.name}
          saving={mcp.saving}
          onCancel={() => mcp.setDeletingServer(null)}
          onConfirm={() => void mcp.confirmDelete()}
        />
      ) : null}
    </ManagementShell>
  )
}
