import { useEffect, useState } from 'react'

import { getOpsPlugins } from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import type { OpsPlugin } from '../../types/ops'
import { formatDateTime } from '../../utils/dateTime'

const timestampFormatter = new Intl.DateTimeFormat()

export function PluginsSection() {
  const { t } = useAppearance()
  const [plugins, setPlugins] = useState<OpsPlugin[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async (refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const response = await getOpsPlugins(refresh)
      setPlugins(response.plugins)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.pluginsLoadFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const validCount = plugins.filter((plugin) => plugin.valid).length
  const toolCount = plugins.reduce((count, plugin) => count + plugin.tools.length, 0)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 border-b border-ops-border/20 pb-4">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.pluginsTitle')}</h4>
          <p className="mt-1 text-[10px] font-medium tracking-wider text-ops-muted opacity-60">
            {t('settings.pluginsDescription')}
          </p>
        </div>
        <button
          type="button"
          className="rounded-lg border border-ops-cyan/30 bg-ops-cyan/10 px-3 py-2 text-[10px] font-bold tracking-widest text-ops-cyan transition-colors hover:bg-ops-cyan/20 disabled:opacity-50"
          disabled={loading}
          onClick={() => void load(true)}
        >
          {t('settings.reloadPlugins')}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          [t('settings.total'), plugins.length],
          [t('settings.valid'), validCount],
          [t('settings.tools'), toolCount],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-ops-border/15 bg-ops-deep/30 px-4 py-3">
            <div className="text-[9px] font-bold tracking-widest text-ops-muted">{label}</div>
            <div className="mt-1 font-mono text-lg font-bold text-ops-cyan">{value}</div>
          </div>
        ))}
      </div>

      {loading ? <div className="py-12 text-center text-sm text-ops-muted">{t('settings.loadingPlugins')}</div> : null}
      {!loading && error ? (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : null}
      {!loading && !error && plugins.length === 0 ? (
        <div className="rounded-xl border border-dashed border-ops-border/20 py-12 text-center text-sm text-ops-muted">
          {t('settings.noPlugins')}
        </div>
      ) : null}

      {!loading && !error ? plugins.map((plugin) => (
        <article
          key={`${plugin.source}-${plugin.id}`}
          className={`rounded-2xl border p-5 ${plugin.valid ? 'border-ops-border/20 bg-ops-panel/40' : 'border-red-500/20 bg-red-500/5'}`}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <strong className="text-[13px] text-ops-text">{plugin.name}</strong>
                <span className="rounded border border-ops-border/20 px-2 py-0.5 font-mono text-[9px] text-ops-muted">
                  {plugin.version}
                </span>
                <span className={`rounded border px-2 py-0.5 text-[9px] font-bold tracking-wider ${plugin.valid && plugin.enabled ? 'border-ops-emerald/20 bg-ops-emerald/10 text-ops-emerald' : 'border-red-500/20 bg-red-500/10 text-red-300'}`}>
                  {plugin.valid && plugin.enabled ? t('settings.enabled') : t('settings.disabled')}
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-5 text-ops-muted">{plugin.description || t('settings.noDescription')}</p>
            </div>
            <div className="text-right text-[9px] tracking-wider text-ops-muted">
              <div>{plugin.source === 'builtin' ? t('settings.builtinPlugin') : t('settings.localPlugin')}</div>
              <div>{formatDateTime(plugin.updatedAt, timestampFormatter, plugin.updatedAt)}</div>
            </div>
          </div>

          {plugin.error ? <div className="mt-4 rounded-lg bg-red-500/10 p-3 text-[11px] text-red-300">{plugin.error}</div> : null}
          {plugin.tools.length ? (
            <div className="mt-4 grid gap-2">
              {plugin.tools.map((tool) => (
                <div key={tool.exposedName} className="rounded-xl border border-ops-border/10 bg-ops-deep/30 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-[10px] font-bold text-ops-cyan">{tool.exposedName}</span>
                    <span className="text-[9px] text-ops-muted">{tool.assetTypes.join(' · ') || t('settings.allAssets')}</span>
                  </div>
                  <p className="mt-1 text-[10px] leading-4 text-ops-muted">{tool.description}</p>
                </div>
              ))}
            </div>
          ) : null}
        </article>
      )) : null}
    </div>
  )
}
