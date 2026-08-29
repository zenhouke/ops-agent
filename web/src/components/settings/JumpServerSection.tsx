import { type FormEvent, useCallback, useEffect, useState } from 'react'
import {
  createJumpServerInstance,
  listJumpServerAssets,
  listJumpServerInstances,
  selectJumpServerAccount,
  syncJumpServerInstance,
  testJumpServerInstance,
  updateJumpServerInstance,
  type JumpServerAssetBinding,
  type JumpServerInstance,
  type JumpServerInstancePayload,
} from '../../api'
import { useAppearance } from '../../hooks/useAppearance'

type FormState = {
  name: string
  authMode: 'access_key' | 'ssh_gateway'
  baseUrl: string
  orgId: string
  accessKeyId: string
  accessKeySecret: string
  verifyTls: boolean
  enabled: boolean
}

const emptyForm: FormState = {
  name: '',
  authMode: 'access_key',
  baseUrl: '',
  orgId: '',
  accessKeyId: '',
  accessKeySecret: '',
  verifyTls: true,
  enabled: true,
}

function accountRef(account: JumpServerAssetBinding['accounts'][number]) {
  return String(account.id || account.name || account.username || '')
}

function accountLabel(account: JumpServerAssetBinding['accounts'][number]) {
  const username = account.username || account.name || account.alias || account.id || ''
  return account.privileged ? `${username} · privileged` : String(username)
}

export function JumpServerSection() {
  const { t } = useAppearance()
  const [instances, setInstances] = useState<JumpServerInstance[]>([])
  const [assets, setAssets] = useState<Record<number, JumpServerAssetBinding[]>>({})
  const [editing, setEditing] = useState<JumpServerInstance | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [accountDrafts, setAccountDrafts] = useState<Record<number, string>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadInstances = useCallback(async () => {
    try {
      setInstances(await listJumpServerInstances())
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.jumpServerLoadFailed'))
    }
  }, [t])

  useEffect(() => { void loadInstances() }, [loadInstances])

  const startCreate = () => {
    setEditing(null)
    setForm(emptyForm)
    setShowForm(true)
    setMessage(null)
  }

  const startEdit = (instance: JumpServerInstance) => {
    setEditing(instance)
    setForm({
      name: instance.name,
      authMode: instance.authMode,
      baseUrl: instance.baseUrl,
      orgId: instance.orgId,
      accessKeyId: instance.accessKeyId,
      accessKeySecret: '',
      verifyTls: instance.verifyTls,
      enabled: instance.enabled,
    })
    setShowForm(true)
    setMessage(null)
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy('save')
    setError(null)
    try {
      const payload: JumpServerInstancePayload = {
        name: form.name,
        auth_mode: form.authMode,
        base_url: form.baseUrl,
        org_id: form.orgId,
        access_key_id: form.accessKeyId,
        verify_tls: form.verifyTls,
        enabled: form.enabled,
        ...(form.accessKeySecret ? { access_key_secret: form.accessKeySecret } : {}),
      }
      if (editing) {
        await updateJumpServerInstance(editing.id, payload)
      } else {
        if (!form.accessKeySecret) throw new Error(t('settings.jumpServerSecretRequired'))
        await createJumpServerInstance(payload)
      }
      await loadInstances()
      setShowForm(false)
      setEditing(null)
      setMessage(t('settings.jumpServerSaved'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.jumpServerSaveFailed'))
    } finally {
      setBusy(null)
    }
  }

  const test = async (instance: JumpServerInstance) => {
    setBusy(`test-${instance.id}`)
    setError(null)
    try {
      const result = await testJumpServerInstance(instance.id)
      if (!result.success) throw new Error(result.message)
      setMessage(result.message)
      await loadInstances()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.jumpServerTestFailed'))
      await loadInstances()
    } finally {
      setBusy(null)
    }
  }

  const loadAssets = async (instance: JumpServerInstance) => {
    setBusy(`assets-${instance.id}`)
    setError(null)
    try {
      const next = await listJumpServerAssets(instance.id)
      setAssets((current) => ({ ...current, [instance.id]: next }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.jumpServerAssetsFailed'))
    } finally {
      setBusy(null)
    }
  }

  const sync = async (instance: JumpServerInstance) => {
    setBusy(`sync-${instance.id}`)
    setError(null)
    try {
      const result = await syncJumpServerInstance(instance.id)
      setMessage(t('settings.jumpServerSyncResult', {
        total: String(result.total),
        created: String(result.created),
        updated: String(result.updated),
        skipped: String(result.skipped),
      }))
      const [nextAssets] = await Promise.all([listJumpServerAssets(instance.id), loadInstances()])
      setAssets((current) => ({ ...current, [instance.id]: nextAssets }))
      window.dispatchEvent(new Event('ops-agent:assets-changed'))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.jumpServerSyncFailed'))
    } finally {
      setBusy(null)
    }
  }

  const changeAccount = async (instanceId: number, binding: JumpServerAssetBinding, ref: string) => {
    setBusy(`account-${binding.id}`)
    setError(null)
    try {
      const updated = await selectJumpServerAccount(binding.id, ref)
      setAssets((current) => ({
        ...current,
        [instanceId]: (current[instanceId] || []).map((item) => item.id === binding.id ? updated : item),
      }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.jumpServerAccountFailed'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4 border-b border-ops-border/20 pb-3">
        <div>
          <h4 className="text-[14px] font-bold text-ops-text">{t('settings.jumpServerTitle')}</h4>
          <p className="mt-1 max-w-xl text-[10px] leading-5 text-ops-muted">{t('settings.jumpServerDescription')}</p>
        </div>
        <button type="button" className="button button-primary shrink-0" onClick={startCreate}>{t('settings.jumpServerAdd')}</button>
      </div>

      {error ? <div className="border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger">{error}</div> : null}
      {message ? <div className="border border-ops-success/30 bg-ops-success/5 px-3 py-2 text-xs text-ops-success">{message}</div> : null}

      {showForm ? (
        <form className="grid grid-cols-2 gap-4 rounded-md border border-ops-border/30 bg-ops-deep/40 p-5" onSubmit={save}>
          <label className="col-span-2 flex flex-col gap-2 text-[10px] font-semibold text-ops-muted">{t('settings.jumpServerAuthMode')}<select className="field-control" value={form.authMode} onChange={(event) => setForm({ ...form, authMode: event.target.value as FormState['authMode'], baseUrl: '' })}><option value="access_key">{t('settings.jumpServerAccessKeyMode')}</option><option value="ssh_gateway">{t('settings.jumpServerSshMode')}</option></select></label>
          <label className="flex flex-col gap-2 text-[10px] font-semibold text-ops-muted">{t('settings.jumpServerName')}<input className="field-control" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label>
          <label className="flex flex-col gap-2 text-[10px] font-semibold text-ops-muted">{form.authMode === 'ssh_gateway' ? t('settings.jumpServerSshAddress') : t('settings.jumpServerBaseUrl')}<input className="field-control" type="url" value={form.baseUrl} onChange={(event) => setForm({ ...form, baseUrl: event.target.value })} placeholder={form.authMode === 'ssh_gateway' ? 'ssh://jumpserver.example.com:2222' : 'https://jumpserver.example.com'} required /></label>
          {form.authMode === 'access_key' ? <label className="flex flex-col gap-2 text-[10px] font-semibold text-ops-muted">{t('settings.jumpServerOrg')}<input className="field-control" value={form.orgId} onChange={(event) => setForm({ ...form, orgId: event.target.value })} placeholder={t('settings.jumpServerOrgPlaceholder')} /></label> : null}
          <label className="flex flex-col gap-2 text-[10px] font-semibold text-ops-muted">{form.authMode === 'ssh_gateway' ? t('settings.jumpServerSshUsername') : 'Access Key ID'}<input className="field-control font-mono" value={form.accessKeyId} onChange={(event) => setForm({ ...form, accessKeyId: event.target.value })} required /></label>
          <label className="col-span-2 flex flex-col gap-2 text-[10px] font-semibold text-ops-muted">{form.authMode === 'ssh_gateway' ? t('settings.jumpServerSshPrivateKey') : 'Access Key Secret'}{form.authMode === 'ssh_gateway' ? <textarea className="field-control min-h-28 font-mono" value={form.accessKeySecret} onChange={(event) => setForm({ ...form, accessKeySecret: event.target.value })} placeholder={editing && editing.authMode === form.authMode ? t('settings.keepUnchanged') : '-----BEGIN ... PRIVATE KEY-----'} required={!editing || editing.authMode !== form.authMode} /> : <input className="field-control font-mono" type="password" value={form.accessKeySecret} onChange={(event) => setForm({ ...form, accessKeySecret: event.target.value })} placeholder={editing && editing.authMode === form.authMode ? t('settings.keepUnchanged') : '••••••••'} required={!editing || editing.authMode !== form.authMode} />}</label>
          {form.authMode === 'access_key' ? <label className="flex items-center gap-2 text-[10px] text-ops-muted"><input type="checkbox" checked={form.verifyTls} onChange={(event) => setForm({ ...form, verifyTls: event.target.checked })} />{t('settings.jumpServerVerifyTls')}</label> : null}
          <label className="flex items-center gap-2 text-[10px] text-ops-muted"><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />{t('settings.jumpServerEnabled')}</label>
          <div className="col-span-2 flex justify-end gap-2 border-t border-ops-border/20 pt-4">
            <button type="button" className="button" onClick={() => setShowForm(false)}>{t('common.cancel')}</button>
            <button type="submit" className="button button-primary" disabled={busy === 'save'}>{busy === 'save' ? t('settings.saving') : t('common.save')}</button>
          </div>
        </form>
      ) : null}

      <div className="flex flex-col gap-3">
        {instances.length === 0 ? <div className="py-12 text-center text-xs text-ops-muted">{t('settings.jumpServerEmpty')}</div> : null}
        {instances.map((instance) => (
          <article key={instance.id} className="rounded-md border border-ops-border/25 bg-ops-panel/35 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <strong className="text-[12px] text-ops-text">{instance.name}</strong>
                  <span className={`rounded px-1.5 py-0.5 text-[8px] ${instance.connectionStatus === 'ok' ? 'bg-ops-success/10 text-ops-success' : instance.connectionStatus === 'failed' ? 'bg-ops-danger/10 text-ops-danger' : 'bg-ops-border/20 text-ops-muted'}`}>{instance.connectionStatus}</span>
                </div>
                <div className="mt-1 font-mono text-[9px] text-ops-muted">{instance.baseUrl} · {instance.authMode === 'ssh_gateway' ? 'SSH Gateway' : 'Access Key'} · {instance.assetCount} assets</div>
                {instance.lastError ? <div className="mt-1 text-[9px] text-ops-danger">{instance.lastError}</div> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="button" onClick={() => startEdit(instance)}>{t('settings.update')}</button>
                <button type="button" className="button" disabled={busy !== null} onClick={() => void test(instance)}>{busy === `test-${instance.id}` ? t('settings.processing') : t('settings.jumpServerTest')}</button>
                <button type="button" className="button" disabled={busy !== null} onClick={() => void loadAssets(instance)}>{t('settings.jumpServerAssets')}</button>
                <button type="button" className="button button-primary" disabled={busy !== null || !instance.enabled} onClick={() => void sync(instance)}>{busy === `sync-${instance.id}` ? t('settings.processing') : t('settings.jumpServerSync')}</button>
              </div>
            </div>

            {assets[instance.id] ? (
              <div className="mt-4 max-h-72 overflow-auto border-t border-ops-border/20 pt-3">
                {assets[instance.id].length === 0 ? <div className="py-6 text-center text-[10px] text-ops-muted">{t('settings.jumpServerNoAssets')}</div> : null}
                {assets[instance.id].map((binding) => (
                  <div key={binding.id} className="grid grid-cols-[minmax(0,1fr)_190px] items-center gap-3 border-b border-ops-border/15 py-2.5 last:border-0">
                    <div className="min-w-0">
                      <div className="truncate text-[11px] font-semibold text-ops-text">{binding.name}</div>
                      <div className="truncate font-mono text-[9px] text-ops-muted">{binding.address} · {binding.platform || binding.type || 'unknown'}{binding.active ? '' : ` · ${t('settings.jumpServerInactive')}`}</div>
                    </div>
                    {instance.authMode === 'ssh_gateway' ? <input className="field-control h-8 text-[10px]" value={accountDrafts[binding.id] ?? binding.accountRef} disabled={!binding.active || busy === `account-${binding.id}`} placeholder={t('settings.jumpServerTargetAccount')} onChange={(event) => setAccountDrafts((current) => ({ ...current, [binding.id]: event.target.value }))} onBlur={(event) => { const value = event.target.value.trim(); if (value && value !== binding.accountRef) void changeAccount(instance.id, binding, value) }} /> : <select className="field-control h-8 text-[10px]" value={binding.accountRef} disabled={!binding.active || busy === `account-${binding.id}`} onChange={(event) => void changeAccount(instance.id, binding, event.target.value)}>
                      {!binding.accountRef ? <option value="">{t('settings.jumpServerNoAccount')}</option> : null}
                      {binding.accounts.filter((account) => account.is_active !== false).map((account) => <option key={accountRef(account)} value={accountRef(account)}>{accountLabel(account)}</option>)}
                    </select>}
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  )
}
