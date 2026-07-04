import { useAppearance } from '../../hooks/useAppearance'
import type { SkillPackage } from '../../types/ops'
import { formatDateTime } from '../../utils/dateTime'
import type { SkillsSectionProps } from './settingsTypes'

const timestampFormatter = new Intl.DateTimeFormat()

function formatBodySize(value: number) {
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function SkillCard({ skill }: { skill: SkillPackage }) {
  const { t } = useAppearance()
  const statusLabel = skill.valid ? t('settings.valid') : t('settings.invalid')
  const statusClasses = skill.valid
    ? 'text-ops-emerald bg-ops-emerald/10 border-ops-emerald/20'
    : 'text-ops-danger bg-ops-danger/10 border-ops-danger/20'

  return (
    <article className={`rounded-2xl border p-5 shadow-sm transition-all duration-300 ${skill.valid ? 'bg-ops-panel/40 border-ops-border/20 hover:border-ops-green/30 hover:bg-ops-panel/60' : 'bg-ops-danger/5 border-ops-danger/20 hover:border-ops-danger/30'}`}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-3">
              <strong className="text-[13px] font-bold text-ops-text tracking-tight break-all">{skill.name}</strong>
              <span className={`px-2 py-0.5 text-[10px] font-bold tracking-widest rounded-md border ${statusClasses}`}>{statusLabel}</span>
            </div>
            <p className="text-[11px] text-ops-muted leading-5">{skill.description || t('settings.noDescription')}</p>
          </div>
        </div>

        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1 rounded-xl border border-ops-border/10 bg-ops-deep/30 px-4 py-3">
            <dt className="text-[10px] font-bold tracking-widest text-ops-muted/70">{t('settings.path')}</dt>
            <dd className="font-mono text-[11px] text-ops-text break-all">{skill.path}</dd>
          </div>
          <div className="flex flex-col gap-1 rounded-xl border border-ops-border/10 bg-ops-deep/30 px-4 py-3">
            <dt className="text-[10px] font-bold tracking-widest text-ops-muted/70">{t('settings.updated')}</dt>
            <dd className="text-[11px] text-ops-text">{formatDateTime(skill.updatedAt, timestampFormatter, skill.updatedAt)}</dd>
          </div>
          <div className="flex flex-col gap-1 rounded-xl border border-ops-border/10 bg-ops-deep/30 px-4 py-3">
            <dt className="text-[10px] font-bold tracking-widest text-ops-muted/70">{t('settings.bodySize')}</dt>
            <dd className="text-[11px] text-ops-text">{formatBodySize(skill.bodySize)}</dd>
          </div>
          <div className="flex flex-col gap-1 rounded-xl border border-ops-border/10 bg-ops-deep/30 px-4 py-3">
            <dt className="text-[10px] font-bold tracking-widest text-ops-muted/70">{t('settings.status')}</dt>
            <dd className={skill.valid ? 'text-[11px] text-ops-emerald' : 'text-[11px] text-ops-danger'}>{statusLabel}</dd>
          </div>
        </dl>

        {!skill.valid && skill.error ? (
          <div className="rounded-xl border border-ops-danger/20 bg-ops-danger/10 px-4 py-3">
            <div className="text-[10px] font-bold tracking-widest text-ops-danger">{t('settings.loadError')}</div>
            <div className="mt-1 text-[11px] text-ops-danger/80 break-words">{skill.error}</div>
          </div>
        ) : null}
      </div>
    </article>
  )
}

export function SkillsSection({ skills, loading, error, onRetry }: SkillsSectionProps) {
  const { t } = useAppearance()
  const validCount = skills.filter((skill) => skill.valid).length
  const invalidCount = skills.length - validCount

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between pb-4 border-b border-ops-border/20">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.skillsTitle')}</h4>
          <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.skillsDescription')}</p>
        </div>
        <div className="text-right text-[10px] font-medium tracking-wider text-ops-muted opacity-70">
          <div>{t('settings.total')}: {skills.length}</div>
          <div>{t('settings.valid')}: {validCount} / {t('settings.invalid')}: {invalidCount}</div>
        </div>
      </div>

      {loading ? <div className="flex items-center justify-center h-40 text-ops-muted text-sm">{t('settings.loadingSkills')}</div> : null}

      {!loading && error ? (
        <div className="p-4 rounded-md bg-ops-danger/10 border border-ops-danger/20 text-ops-danger text-sm flex items-center justify-between gap-4">
          <span>{error}</span>
          <button type="button" className="px-3 py-1.5 rounded-md bg-ops-border/20 hover:bg-ops-border/30 transition-colors text-ops-text text-sm" onClick={onRetry}>{t('common.retry')}</button>
        </div>
      ) : null}

      {!loading && !error && skills.length === 0 ? (
        <div className="text-center py-10 text-ops-muted text-sm bg-ops-panel/20 rounded-lg border border-ops-border/10 border-dashed">{t('settings.noSkillPackages')}</div>
      ) : null}

      {!loading && !error ? (
        <div className="flex flex-col gap-3">
          {skills.map((skill) => <SkillCard key={`${skill.path}-${skill.name}`} skill={skill} />)}
        </div>
      ) : null}
    </div>
  )
}
