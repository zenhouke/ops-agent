import { useAppearance } from '../../hooks/useAppearance'
import type { MCPServer, MCPTool } from '../../types/ops'
import type { MCPSectionProps } from './settingsTypes'

function statusClass(status: string) {
  if (status === 'ok') {
    return 'text-ops-emerald bg-ops-emerald/10 border-ops-emerald/20'
  }
  if (status === 'failed') {
    return 'text-ops-danger bg-ops-danger/10 border-ops-danger/20'
  }
  return 'text-ops-muted bg-ops-border/10 border-ops-border/20'
}

function transportLabel(server: MCPServer) {
  return server.transport === 'httpSse' ? 'HTTP/SSE' : 'stdio'
}

function summarizeSchema(tool: MCPTool, t: ReturnType<typeof useAppearance>['t']) {
  const properties = tool.inputSchema.properties
  if (properties && typeof properties === 'object' && !Array.isArray(properties)) {
    const keys = Object.keys(properties)
    return keys.length ? `schema: ${keys.slice(0, 6).join(', ')}${keys.length > 6 ? '…' : ''}` : t('settings.schemaNoProperties')
  }
  return Object.keys(tool.inputSchema).length ? t('settings.schemaAvailable') : t('settings.schemaEmpty')
}

function ServerCard({ server, selected, saving, onSelect, onEdit, onDelete, onTest, onRefresh, onSetEnabled }: {
  server: MCPServer
  selected: boolean
  saving: boolean
  onSelect: (serverId: string) => void
  onEdit: (server: MCPServer) => void
  onDelete: (server: MCPServer) => void
  onTest: (server: MCPServer) => void
  onRefresh: (server: MCPServer) => void
  onSetEnabled: (server: MCPServer, enabled: boolean) => void
}) {
  const { t } = useAppearance()
  const enableBlocked = !server.enabled && !server.lastRefreshSucceeded

  return (
    <article className={`rounded-2xl border p-5 shadow-sm transition-all duration-300 ${selected ? 'bg-ops-green/5 border-ops-green/30' : 'bg-ops-panel/40 border-ops-border/20 hover:border-ops-green/30 hover:bg-ops-panel/60'}`}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onSelect(server.id)}>
            <div className="flex flex-wrap items-center gap-3">
              <strong className="text-[13px] font-bold text-ops-text tracking-tight break-all">{server.name}</strong>
              <span className="px-2 py-0.5 text-[10px] font-bold tracking-widest rounded-md text-ops-green bg-ops-green/10 border border-ops-green/20">{transportLabel(server)}</span>
              <span className={`px-2 py-0.5 text-[10px] font-bold tracking-widest rounded-md border ${server.enabled ? 'text-ops-emerald bg-ops-emerald/10 border-ops-emerald/20' : 'text-ops-muted bg-ops-border/10 border-ops-border/20'}`}>{server.enabled ? t('settings.enabled') : t('settings.disabled')}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-medium tracking-wider text-ops-muted">
              <span className={`px-2 py-0.5 rounded-md border ${statusClass(server.connectionStatus)}`}>{t('settings.connection')}: {server.connectionStatus}</span>
              <span className={`px-2 py-0.5 rounded-md border ${statusClass(server.discoveryStatus)}`}>{t('settings.discovery')}: {server.discoveryStatus}</span>
              <span className="px-2 py-0.5 rounded-md border border-ops-border/20 bg-ops-deep/30">{t('settings.tools')}: {server.tools.length}</span>
            </div>
          </button>
          <div className="flex flex-col items-end gap-2">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button type="button" className="button h-8 px-3 text-[10px]" onClick={() => onSetEnabled(server, !server.enabled)} disabled={saving || enableBlocked} title={enableBlocked ? t('settings.enableBlocked') : undefined}>{server.enabled ? t('settings.disable') : t('settings.enable')}</button>
              <button type="button" className="button h-8 px-3 text-[10px]" onClick={() => onTest(server)} disabled={saving}>{t('common.test')}</button>
              <button type="button" className="button h-8 px-3 text-[10px]" onClick={() => onRefresh(server)} disabled={saving}>{t('common.refresh')}</button>
              <button type="button" className="button h-8 px-3 text-[10px]" onClick={() => onEdit(server)}>{t('common.edit')}</button>
              <button type="button" className="button button-danger h-8 px-3 text-[10px]" onClick={() => onDelete(server)} disabled={saving}>{t('common.delete')}</button>
            </div>
            {enableBlocked ? <div className="max-w-[220px] text-right text-[10px] leading-4 text-ops-muted">{t('settings.enableBlocked')}</div> : null}
          </div>
        </div>
        {server.lastError ? (
          <div className="rounded-xl border border-ops-danger/20 bg-ops-danger/10 px-4 py-3 text-[11px] text-ops-danger break-words">{server.lastError}</div>
        ) : null}
      </div>
    </article>
  )
}

export function McpSection({
  servers,
  serverForm,
  showServerForm,
  editingServer,
  selectedServerId,
  loading,
  error,
  saving,
  testResult,
  onRetry,
  onStartCreate,
  onStartEdit,
  onStartDelete,
  onSelectServer,
  onFormChange,
  onCancelForm,
  onSave,
  onTest,
  onRefresh,
  onSetEnabled,
  onUpdateTool,
}: MCPSectionProps) {
  const { t } = useAppearance()
  const selectedServer = servers.find((server) => server.id === selectedServerId) ?? servers[0] ?? null

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between pb-4 border-b border-ops-border/20">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.mcpServersTitle')}</h4>
          <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.mcpServersDescription')}</p>
        </div>
        <button type="button" className="button button-primary" onClick={onStartCreate}>{t('settings.addMcpServer')}</button>
      </div>

      {loading ? <div className="flex items-center justify-center h-40 text-ops-muted text-sm">{t('settings.loadingMcpServers')}</div> : null}

      {!loading && error ? (
        <div className="p-4 rounded-md bg-ops-danger/10 border border-ops-danger/20 text-ops-danger text-sm flex items-center justify-between gap-4">
          <span>{error}</span>
          <button type="button" className="px-3 py-1.5 rounded-md bg-ops-border/20 hover:bg-ops-border/30 transition-colors text-ops-text text-sm" onClick={onRetry}>{t('common.retry')}</button>
        </div>
      ) : null}

      {!loading && !error && showServerForm ? (
        <form className="bg-ops-deep/40 p-6 rounded-2xl border border-ops-border/20 grid grid-cols-2 gap-5 mt-2 animate-in slide-in-from-top-4 duration-300" onSubmit={onSave}>
          <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70">
            {t('settings.serverName')}
            <input className="field-control" value={serverForm.name} onChange={(event) => onFormChange({ ...serverForm, name: event.target.value })} placeholder="e.g. filesystem" required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70">
            {t('settings.transport')}
            <select className="field-control" value={serverForm.transport} onChange={(event) => onFormChange({ ...serverForm, transport: event.target.value === 'httpSse' ? 'httpSse' : 'stdio' })}>
              <option value="stdio">stdio</option>
              <option value="httpSse">HTTP/SSE</option>
            </select>
          </label>

          {serverForm.transport === 'stdio' ? (
            <>
              <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70 col-span-2">
                {t('settings.command')}
                <input className="field-control font-mono" value={serverForm.command} onChange={(event) => onFormChange({ ...serverForm, command: event.target.value })} placeholder="npx" required />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70 col-span-2">
                {t('settings.argsOnePerLine')}
                <textarea className="field-control min-h-[84px] font-mono" value={serverForm.args} onChange={(event) => onFormChange({ ...serverForm, args: event.target.value })} placeholder="-y&#10;@modelcontextprotocol/server-filesystem" rows={4} />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70 col-span-2">
                {t('settings.envJson')}
                <textarea className="field-control min-h-[84px] font-mono" value={serverForm.env} onChange={(event) => onFormChange({ ...serverForm, env: event.target.value })} placeholder={'{\n  "TOKEN": "redacted"\n}'} rows={4} />
              </label>
            </>
          ) : (
            <>
              <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70 col-span-2">
                URL
                <input className="field-control font-mono" value={serverForm.url} onChange={(event) => onFormChange({ ...serverForm, url: event.target.value })} placeholder="https://example.com/sse" required />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70 col-span-2">
                {t('settings.headersJson')}
                <textarea className="field-control min-h-[84px] font-mono" value={serverForm.headers} onChange={(event) => onFormChange({ ...serverForm, headers: event.target.value })} placeholder={'{\n  "Authorization": "Bearer redacted"\n}'} rows={4} />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70">
                {t('settings.timeoutSeconds')}
                <input className="field-control font-mono" type="number" min="1" value={serverForm.timeoutSeconds} onChange={(event) => onFormChange({ ...serverForm, timeoutSeconds: event.target.value })} required />
              </label>
            </>
          )}

          {testResult ? <div className="col-span-2 p-4 text-[11px] font-mono text-ops-green bg-ops-green/10 border border-ops-green/20 rounded-xl break-all animate-in fade-in duration-300">{testResult}</div> : null}
          <div className="flex items-center justify-end gap-3 mt-4 pt-6 border-t border-ops-border/20 col-span-2">
            <button type="button" className="button px-6" onClick={onCancelForm}>{t('common.cancel')}</button>
            <button type="submit" className="button button-primary px-8" disabled={saving}>{saving ? t('settings.processing') : editingServer ? t('settings.saveServer') : t('settings.createServer')}</button>
          </div>
        </form>
      ) : null}

      {!loading && !error && servers.length === 0 ? (
        <div className="text-center py-10 text-ops-muted text-sm bg-ops-panel/20 rounded-lg border border-ops-border/10 border-dashed">{t('settings.noMcpServers')}</div>
      ) : !loading && !error ? (
        <div className="flex flex-col gap-3">
          {servers.map((server) => (
            <ServerCard
              key={server.id}
              server={server}
              selected={selectedServer?.id === server.id}
              saving={saving}
              onSelect={onSelectServer}
              onEdit={onStartEdit}
              onDelete={onStartDelete}
              onTest={onTest}
              onRefresh={onRefresh}
              onSetEnabled={onSetEnabled}
            />
          ))}
        </div>
      ) : null}

      {!loading && !error && selectedServer ? (
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between pb-3 border-b border-ops-border/20">
            <div>
              <h5 className="text-[12px] font-bold tracking-[0.14em] text-ops-text">{t('settings.toolsForServer', { name: selectedServer.name })}</h5>
              <p className="text-[10px] text-ops-muted mt-1">{t('settings.toolsDescription')}</p>
            </div>
          </div>
          {selectedServer.tools.length === 0 ? (
            <div className="text-center py-6 text-ops-muted text-sm bg-ops-panel/20 rounded-lg border border-ops-border/10 border-dashed">{t('settings.noTools')}</div>
          ) : (
            <div className="flex flex-col gap-3">
              {selectedServer.tools.map((tool) => (
                <article key={tool.id} className="rounded-2xl border border-ops-border/20 bg-ops-panel/40 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <strong className="text-[12px] text-ops-text break-all">{tool.exposedName}</strong>
                        <span className="text-[10px] text-ops-muted font-mono break-all">{t('settings.original')}: {tool.originalName}</span>
                        <span className={`px-2 py-0.5 text-[10px] font-bold tracking-widest rounded-md border ${tool.enabled ? 'text-ops-emerald bg-ops-emerald/10 border-ops-emerald/20' : 'text-ops-muted bg-ops-border/10 border-ops-border/20'}`}>{tool.enabled ? t('settings.enabled') : t('settings.disabled')}</span>
                      </div>
                      <p className="mt-2 text-[11px] leading-5 text-ops-muted">{tool.description || t('settings.noDescription')}</p>
                      <p className="mt-1 text-[10px] font-mono text-ops-muted/80">{summarizeSchema(tool, t)}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="flex items-center gap-2 text-[10px] font-bold tracking-widest text-ops-muted/70">
                        <input type="checkbox" className="accent-ops-green w-4 h-4 rounded-md" checked={tool.enabled} onChange={(event) => onUpdateTool(tool, { enabled: event.target.checked })} disabled={saving} />
                        Enabled
                      </label>
                      <select className="field-control h-8 py-0 text-[10px]" value={tool.approvalPolicy} onChange={(event) => onUpdateTool(tool, { approvalPolicy: event.target.value === 'allow' ? 'allow' : event.target.value === 'deny' ? 'deny' : 'ask' })} disabled={saving}>
                        <option value="ask">{t('settings.askApproval')}</option>
                        <option value="allow">{t('settings.allow')}</option>
                        <option value="deny">{t('settings.deny')}</option>
                      </select>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}
