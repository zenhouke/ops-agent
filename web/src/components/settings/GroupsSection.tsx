import type { GroupForm, GroupsSectionProps } from './settingsTypes'
import { useAppearance } from '../../hooks/useAppearance'

export function GroupsSection({
  groups,
  groupForm,
  showGroupForm,
  saving,
  onStartCreate,
  onStartEdit,
  onStartDelete,
  onFormChange,
  onCancelForm,
  onSave,
}: GroupsSectionProps) {
  const { t } = useAppearance()
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between border-b border-ops-border/20 pb-3">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.groupsTitle')}</h4>
          <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.groupsDescription')}</p>
        </div>
        <button type="button" className="button button-primary" onClick={onStartCreate}>{t('settings.newGroup')}</button>
      </div>

      {showGroupForm ? (
        <form className="flex flex-col gap-5 rounded-md border border-ops-border/30 bg-ops-deep/40 p-5" onSubmit={onSave}>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.groupLabel')}
            <input className="field-control" value={groupForm.name} onChange={(event) => onFormChange({ ...groupForm, name: event.target.value })} placeholder={t('settings.groupLabelPlaceholder')} required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70">TCP Proxy
            <select className="field-control" value={groupForm.proxy_type} onChange={(event) => onFormChange({ ...groupForm, proxy_type: event.target.value as GroupForm['proxy_type'] })}>
              <option value="none">Direct connection</option><option value="http_connect">HTTP CONNECT</option><option value="socks5">SOCKS5</option>
            </select>
          </label>
          {groupForm.proxy_type !== 'none' ? <>
            <input className="field-control" placeholder="Proxy host" value={groupForm.proxy_host} onChange={(event) => onFormChange({ ...groupForm, proxy_host: event.target.value })} required />
            <input className="field-control" type="number" min="1" max="65535" placeholder="Proxy port" value={groupForm.proxy_port} onChange={(event) => onFormChange({ ...groupForm, proxy_port: event.target.value })} required />
            <input className="field-control" placeholder="Proxy username" value={groupForm.proxy_username} onChange={(event) => onFormChange({ ...groupForm, proxy_username: event.target.value })} />
            <input className="field-control" type="password" placeholder="Proxy password" value={groupForm.proxy_password} onChange={(event) => onFormChange({ ...groupForm, proxy_password: event.target.value })} />
          </> : null}
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.groupDescription')}
            <textarea className="field-control min-h-[80px]" value={groupForm.description} onChange={(event) => onFormChange({ ...groupForm, description: event.target.value })} placeholder={t('settings.groupDescriptionPlaceholder')} rows={3} />
          </label>
          <div className="flex items-center justify-end gap-3 mt-2 pt-4 border-t border-ops-border/20">
            <button type="button" className="button px-6" onClick={onCancelForm}>{t('common.cancel')}</button>
            <button type="submit" className="button button-primary px-8" disabled={saving}>{saving ? t('settings.processing') : t('settings.saveGroup')}</button>
          </div>
        </form>
      ) : null}

      {groups.length === 0 ? <div className="text-center py-10 text-ops-muted text-sm bg-ops-panel/20 rounded-lg border border-ops-border/10 border-dashed">{t('settings.noGroups')}</div> : null}
      <div className="flex flex-col gap-1.5">
        {groups.map((group) => (
          <article key={group.id} className="group flex items-center justify-between rounded-md border border-ops-border/25 bg-ops-panel/35 px-3 py-3 transition-all duration-200 hover:border-ops-text/20 hover:bg-ops-panel/60">
            <div className="flex flex-col gap-1.5">
              <strong className="text-[13px] font-bold text-ops-text tracking-tight">{group.name}</strong>
              {group.description ? <span className="text-[10px] text-ops-muted font-bold  tracking-widest opacity-60">{group.description === '默认分组' ? t('settings.defaultGroup') : group.description}</span> : null}
            </div>
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-all duration-200">
              <button type="button" className="button h-8 px-4 text-[10px]" onClick={() => onStartEdit(group)}>{t('common.edit')}</button>
              <button type="button" className="button button-danger h-8 px-4 text-[10px]" onClick={() => onStartDelete(group)}>{t('common.delete')}</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
