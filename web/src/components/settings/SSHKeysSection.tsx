import type { SSHKeysSectionProps } from './settingsTypes'
import { useAppearance } from '../../hooks/useAppearance'

export function SSHKeysSection({ sshKeys, sshKeyForm, showSSHKeyForm, editingSSHKey, saving, onStartCreate, onStartEdit, onStartDelete, onFormChange, onCancelForm, onSave }: SSHKeysSectionProps) {
  const { t } = useAppearance()
  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-center justify-between border-b border-ops-border/20 pb-3">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.sshKeysTitle')}</h4>
          <p className="text-[10px] font-medium text-ops-muted mt-1 tracking-wider opacity-60">{t('settings.sshKeysDescription')}</p>
        </div>
        <button type="button" className="button button-primary" onClick={onStartCreate}>{t('settings.provisionNewKey')}</button>
      </div>

      {showSSHKeyForm ? (
        <form className="flex flex-col gap-5 rounded-md border border-ops-border/30 bg-ops-deep/40 p-5" onSubmit={onSave}>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.keyIdentifier')}
            <input className="field-control" value={sshKeyForm.name} onChange={(event) => onFormChange({ ...sshKeyForm, name: event.target.value })} placeholder="e.g. ops-master-key" required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.publicKey')}
            <textarea className="field-control font-mono min-h-[80px]" value={sshKeyForm.publicKey} onChange={(event) => onFormChange({ ...sshKeyForm, publicKey: event.target.value })} placeholder="ssh-rsa AAAA..." rows={3} required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.privateKey')}
            <textarea className="field-control font-mono min-h-[120px]" value={sshKeyForm.privateKey} onChange={(event) => onFormChange({ ...sshKeyForm, privateKey: event.target.value })} placeholder={editingSSHKey ? t('settings.keepUnchanged') : '-----BEGIN OPENSSH PRIVATE KEY-----'} rows={6} required={!editingSSHKey} />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70">
            {t('settings.keyPassphrase')}
            <input className="field-control font-mono" type="password" value={sshKeyForm.passphrase} onChange={(event) => onFormChange({ ...sshKeyForm, passphrase: event.target.value })} placeholder="••••••••••••" />
          </label>
          <div className="flex items-center justify-end gap-3 mt-2 pt-4 border-t border-ops-border/20">
            <button type="button" className="button px-6" onClick={onCancelForm}>{t('common.cancel')}</button>
            <button type="submit" className="button button-primary px-8" disabled={saving}>{saving ? t('settings.processing') : t('settings.authorizeKey')}</button>
          </div>
        </form>
      ) : null}

      <div className="flex flex-col gap-1.5">
        {sshKeys.map((sshKey) => (
          <article key={sshKey.id} className="group flex items-center justify-between rounded-md border border-ops-border/25 bg-ops-panel/35 px-3 py-3 transition-all duration-200 hover:border-ops-text/20 hover:bg-ops-panel/60">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded border border-ops-border/30 bg-ops-deep text-ops-muted transition-colors group-hover:text-ops-text">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="15" r="4" /><path d="m11 12 8-8M15 8l2 2M17 6l2 2" /></svg>
              </div>
              <div className="flex min-w-0 flex-col gap-1">
                <strong className="truncate text-[12px] font-semibold text-ops-text">{sshKey.name}</strong>
                <span className="max-w-[520px] truncate font-mono text-[9px] text-ops-muted/55">{sshKey.publicKey.substring(0, 64)}...</span>
              </div>
            </div>
            <div className="flex items-center gap-2 opacity-0 transition-all duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
              <button type="button" className="button h-8 px-4 text-[10px]" onClick={() => onStartEdit(sshKey)}>{t('settings.update')}</button>
              <button type="button" className="button button-danger h-8 px-4 text-[10px]" onClick={() => onStartDelete(sshKey)}>{t('settings.revoke')}</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
