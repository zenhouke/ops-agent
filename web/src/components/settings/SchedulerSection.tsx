import { type FormEvent, useEffect, useState } from 'react'
import {
  createScheduledJob,
  deleteScheduledJob,
  getScheduledJobs,
  triggerScheduledJob,
  updateScheduledJob,
} from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import type { Asset } from '../../types/ops'
import type { ScheduledJob } from '../../types/alerts'

type SchedulerSectionProps = {
  assets: Asset[]
}

const PRESET_PROMPTS = [
  {
    label: '磁盘空间与负载巡检',
    value: '请对系统进行健康检查。主要检查 CPU 负载、内存使用率和磁盘空间。如果发现任何磁盘分区使用率超过 85%，或 CPU 平均负载过高，请输出 [ALERT: 系统资源不足] 分区使用率与负载详情。如果正常则输出 [OK]。',
  },
  {
    label: '系统安全日志审计',
    value: '检查系统的安全日志与 SSH 登录记录（如 /var/log/auth.log 或 journalctl）。分析是否有大量失败的登录尝试。如果发现可疑的暴力破解迹象，请输出 [ALERT: 安全审计告警] 发现来自 IP xxx 的多次登录失败。如果无异常则输出 [OK]。',
  },
  {
    label: '关键服务状态检查',
    value: '检查系统中关键服务（如 docker, nginx, mysql）的运行状态。如果发现服务处于 inactive 或 error 状态，请输出 [ALERT: 服务停用] 服务名处于停止状态。如果全部运行正常则请输出 [OK]。',
  },
]

export function SchedulerSection({ assets }: SchedulerSectionProps) {
  const { t } = useAppearance()
  const [jobs, setJobs] = useState<ScheduledJob[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null)
  const [triggeringId, setTriggeringId] = useState<number | null>(null)
  const [triggerStatus, setTriggerStatus] = useState<Record<number, string>>({})

  // Form State
  const [name, setName] = useState('')
  const [assetId, setAssetId] = useState<number>(assets[0]?.id ?? 0)
  const [prompt, setPrompt] = useState(PRESET_PROMPTS[0].value)
  const [intervalSeconds, setIntervalSeconds] = useState(3600)
  const [enabled, setEnabled] = useState(true)
  const hasAssets = assets.length > 0

  const loadJobs = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getScheduledJobs()
      setJobs(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('scheduler.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadJobs()
  }, [])

  const startCreate = () => {
    if (!hasAssets) {
      setError(t('scheduler.noAssetsHelp'))
      return
    }
    setEditingJob(null)
    setName('')
    setAssetId(assets[0]?.id ?? 0)
    setPrompt(PRESET_PROMPTS[0].value)
    setIntervalSeconds(3600)
    setEnabled(true)
    setShowForm(true)
  }

  const startEdit = (job: ScheduledJob) => {
    setEditingJob(job)
    setName(job.name)
    setAssetId(job.assetId)
    setPrompt(job.prompt)
    setIntervalSeconds(job.intervalSeconds)
    setEnabled(job.enabled)
    setShowForm(true)
  }

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !prompt.trim() || !assetId) {
      return
    }

    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: name.trim(),
        asset_id: assetId,
        prompt: prompt.trim(),
        interval_seconds: Number(intervalSeconds),
        enabled,
      }

      if (editingJob) {
        const updated = await updateScheduledJob(editingJob.id, payload)
        setJobs(jobs.map((j) => (j.id === updated.id ? updated : j)))
      } else {
        const created = await createScheduledJob(payload)
        setJobs([created, ...jobs])
      }
      setShowForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('scheduler.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('scheduler.confirmDelete'))) {
      return
    }
    setError(null)
    try {
      await deleteScheduledJob(id)
      setJobs(jobs.filter((j) => j.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : t('scheduler.deleteFailed'))
    }
  }

  const handleTrigger = async (id: number) => {
    setTriggeringId(id)
    setTriggerStatus((prev) => ({ ...prev, [id]: t('scheduler.triggering') }))
    try {
      await triggerScheduledJob(id)
      setTriggerStatus((prev) => ({ ...prev, [id]: t('scheduler.triggered') }))
      setTimeout(() => {
        setTriggerStatus((prev) => {
          const next = { ...prev }
          delete next[id]
          return next
        })
      }, 3000)
    } catch (err) {
      setTriggerStatus((prev) => ({
        ...prev,
        [id]: err instanceof Error ? t('scheduler.triggerFailedWithMessage', { message: err.message }) : t('scheduler.triggerFailed'),
      }))
    } finally {
      setTriggeringId(null)
    }
  }

  const getAssetName = (id: number) => {
    return assets.find((a) => a.id === id)?.name ?? t('scheduler.assetFallback', { id: String(id) })
  }

  const formatInterval = (seconds: number) => {
    if (seconds < 60) return t('scheduler.seconds', { count: String(seconds) })
    if (seconds < 3600) return t('scheduler.minutes', { count: String(Math.round(seconds / 60)) })
    if (seconds < 86400) return t('scheduler.hours', { count: String(Math.round(seconds / 3600)) })
    return t('scheduler.days', { count: String(Math.round(seconds / 86400)) })
  }

  const formatTime = (isoString: string | null) => {
    if (!isoString) return t('scheduler.neverRun')
    try {
      const date = new Date(isoString)
      return date.toLocaleString()
    } catch {
      return t('scheduler.unknownTime')
    }
  }

  return (
    <div className="flex flex-col h-full space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h4 className="text-xs font-bold text-ops-green tracking-wider">{t('scheduler.title')}</h4>
          <p className="text-[10px] text-ops-muted mt-0.5">{t('scheduler.description')}</p>
        </div>
        {!showForm && (
          <button
            type="button"
            onClick={startCreate}
            disabled={!hasAssets}
            className="button h-8 px-4 text-[10px] font-black tracking-widest text-ops-green border border-ops-green/35 bg-ops-green/10 hover:bg-ops-green/20 active:scale-95 transition-all disabled:opacity-40"
          >
            {t('scheduler.newJob')}
          </button>
        )}
      </div>

      {!hasAssets ? (
        <div className="rounded-lg border border-ops-warning/25 bg-ops-warning/10 p-3 text-[11px] font-bold text-ops-warning">
          {t('scheduler.noAssetsHelp')}
        </div>
      ) : null}

      {error && (
        <div className="p-3 rounded-lg border border-ops-danger/30 bg-ops-danger/10 text-ops-danger text-[11px] font-bold">
          {error}
        </div>
      )}

      {showForm ? (
        <form onSubmit={handleSave} className="bg-ops-deep/40 border border-ops-border/20 rounded-xl p-4 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="text-xs font-bold text-ops-text pb-2 border-b border-ops-border/10">
            {editingJob ? t('scheduler.editJob') : t('scheduler.createJob')}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="flex flex-col space-y-1.5">
              <label className="text-[10px] font-black text-ops-muted tracking-wider">{t('scheduler.jobName')}</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('scheduler.jobNamePlaceholder')}
                className="h-9 w-full rounded-lg bg-ops-deep px-3 text-[11px] font-medium text-ops-text border border-ops-border/20 focus:border-ops-green/40 focus:ring-1 focus:ring-ops-green/35 transition-all outline-none"
              />
            </div>

            <div className="flex flex-col space-y-1.5">
              <label className="text-[10px] font-black text-ops-muted tracking-wider">{t('scheduler.asset')}</label>
              <select
                value={assetId}
                onChange={(e) => setAssetId(Number(e.target.value))}
                className="h-9 w-full rounded-lg bg-ops-deep px-3 text-[11px] font-medium text-ops-text border border-ops-border/20 focus:border-ops-green/40 outline-none"
              >
                {assets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.name} ({asset.assetType})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="flex flex-col space-y-1.5">
              <label className="text-[10px] font-black text-ops-muted tracking-wider">{t('scheduler.interval')}</label>
              <select
                value={intervalSeconds}
                onChange={(e) => setIntervalSeconds(Number(e.target.value))}
                className="h-9 w-full rounded-lg bg-ops-deep px-3 text-[11px] font-medium text-ops-text border border-ops-border/20 focus:border-ops-green/40 outline-none"
              >
                <option value={60}>{t('scheduler.everyMinute')}</option>
                <option value={300}>{t('scheduler.everyFiveMinutes')}</option>
                <option value={900}>{t('scheduler.everyFifteenMinutes')}</option>
                <option value={1800}>{t('scheduler.everyThirtyMinutes')}</option>
                <option value={3600}>{t('scheduler.hourly')}</option>
                <option value={43200}>{t('scheduler.everyTwelveHours')}</option>
                <option value={86400}>{t('scheduler.daily')}</option>
              </select>
            </div>

            <div className="flex items-center gap-2 pt-6">
              <input
                type="checkbox"
                id="job-enabled"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-ops-border/40 bg-ops-deep text-ops-green outline-none"
              />
              <label htmlFor="job-enabled" className="text-[11px] font-bold text-ops-text cursor-pointer select-none">
                {t('scheduler.enableJob')}
              </label>
            </div>
          </div>

          <div className="flex flex-col space-y-1.5">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <label className="text-[10px] font-black text-ops-muted tracking-wider">{t('scheduler.prompt')}</label>
              <div className="flex flex-wrap gap-2">
                {PRESET_PROMPTS.map((preset, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setPrompt(preset.value)}
                    className="text-[10px] font-bold text-ops-green/80 hover:text-ops-green transition-colors"
                  >
                    [{preset.label}]
                  </button>
                ))}
              </div>
            </div>
            <textarea
              required
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t('scheduler.promptPlaceholder')}
              className="w-full rounded-lg bg-ops-deep p-3 text-[11px] font-medium text-ops-text border border-ops-border/20 focus:border-ops-green/40 focus:ring-1 focus:ring-ops-green/35 transition-all outline-none resize-y"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="button h-8 px-4 text-[10px] font-bold text-ops-muted hover:text-ops-text active:scale-95 transition-all"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="button h-8 px-5 text-[10px] font-bold text-ops-text bg-ops-green/20 border border-ops-green/40 hover:bg-ops-green/35 active:scale-95 transition-all disabled:opacity-50"
            >
              {saving ? t('settings.saving') : t('scheduler.confirmSave')}
            </button>
          </div>
        </form>
      ) : null}

      {!showForm && (
        <div className="flex-1 overflow-y-auto custom-scrollbar border border-ops-border/15 rounded-xl bg-ops-panel/20">
          {loading ? (
            <div className="flex items-center justify-center h-48 text-ops-muted text-[11px] font-bold">
              {t('scheduler.loadingJobs')}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-ops-muted/40">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mb-2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              <p className="text-[10px] font-bold tracking-wider">{t('scheduler.empty')}</p>
            </div>
          ) : (
            <div className="divide-y divide-ops-border/10">
              {jobs.map((job) => (
                <div key={job.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-ops-deep/10 hover:bg-ops-deep/20 transition-all">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-bold tracking-wide border ${
                        job.enabled
                          ? 'border-ops-emerald/30 bg-ops-emerald/10 text-ops-emerald'
                          : 'border-ops-border/30 bg-ops-border/10 text-ops-muted'
                      }`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${job.enabled ? 'bg-ops-emerald' : 'bg-ops-muted'}`} />
                        {job.enabled ? t('settings.enabled') : t('settings.disabled')}
                      </span>
                      <h5 className="text-[12px] font-black text-ops-text">{job.name}</h5>
                    </div>

                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ops-muted font-medium pt-1">
                      <span>{t('scheduler.assetLabel')} <strong className="text-ops-green/90 font-bold">{getAssetName(job.assetId)}</strong></span>
                      <span>{t('scheduler.intervalLabel')} <strong className="text-ops-text font-bold">{formatInterval(job.intervalSeconds)}</strong></span>
                      <span>{t('scheduler.lastRunLabel')} <strong className="text-ops-text font-bold">{formatTime(job.lastRunAt)}</strong></span>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    {triggerStatus[job.id] ? (
                      <span className="text-[10px] font-bold text-ops-green bg-ops-green/10 border border-ops-green/20 px-2 py-1 rounded">
                        {triggerStatus[job.id]}
                      </span>
                    ) : null}

                    <button
                      type="button"
                      disabled={triggeringId !== null}
                      onClick={() => handleTrigger(job.id)}
                      className="button-mini button-mini-primary h-7 px-3 text-[10px]"
                    >
                      {t('scheduler.triggerNow')}
                    </button>
                    <button
                      type="button"
                      onClick={() => startEdit(job)}
                      className="button-mini h-7 px-3 text-[10px]"
                    >
                      {t('common.edit')}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(job.id)}
                      className="button-mini button-mini-danger h-7 px-3 text-[10px]"
                    >
                      {t('common.delete')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
