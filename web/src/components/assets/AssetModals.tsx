import { type FormEvent, forwardRef, useEffect, useImperativeHandle, useState } from 'react'
import { getSerialPorts, type SerialPort } from '../../api'
import type { Asset, AssetGroup, SSHKey } from '../../types/ops'
import { useAppearance } from '../../hooks/useAppearance'

type ActiveModal = 'add-asset' | 'edit-asset' | 'delete-asset' | null

type ConnectionMode = 'ssh' | 'serial'
type AssetKind = 'linux' | 'network' | 'cisco' | 'huawei' | 'juniper' | 'h3c' | 'serial'

type AddAssetForm = {
  mode: ConnectionMode
  assetKind: AssetKind
  name: string
  host: string
  port: string
  username: string
  authType: string
  credentialSecret: string
  sshKeyId: string
  proxyAssetId: string
  serialPort: string
  baudRate: string
  dataBits: string
  parity: string
  stopBits: string
  groupId: string
}

const emptyAddAssetForm: AddAssetForm = {
  mode: 'ssh',
  assetKind: 'linux',
  name: '',
  host: '',
  port: '22',
  username: '',
  authType: 'password',
  credentialSecret: '',
  sshKeyId: '',
  proxyAssetId: '',
  serialPort: '',
  baudRate: '9600',
  dataBits: '8',
  parity: 'none',
  stopBits: '1',
  groupId: '',
}

function supportsSshProxyTarget(assetKind: AssetKind): boolean {
  return ['linux', 'network', 'cisco', 'huawei', 'juniper', 'h3c'].includes(assetKind)
}

function isProxyCandidate(asset: Asset, targetAssetId: number | null): boolean {
  return asset.id !== targetAssetId && asset.proxyAssetId === null && asset.assetType === 'linux'
}

function buildConnectionTags(form: AddAssetForm): string[] {
  if (form.mode === 'serial') {
    return [
      'connection:serial',
      `data-bits:${form.dataBits}`,
      `parity:${form.parity}`,
      `stop-bits:${form.stopBits}`,
    ]
  }

  return ['connection:ssh']
}

export interface AssetModalsRef {
  openAddModal: () => void
  openEditModal: (asset: Asset) => void
  openDeleteModal: (asset: Asset) => void
}

interface AssetModalsProps {
  assets: Asset[]
  groups: AssetGroup[]
  sshKeys: SSHKey[]
  onAddAsset: (payload: any) => Promise<void>
  onUpdateAsset: (id: number, payload: any) => Promise<void>
  onDeleteAsset: (id: number) => Promise<void>
}

type AssetFormModalProps = {
  mode: 'add-asset' | 'edit-asset'
  form: AddAssetForm
  assets: Asset[]
  targetAsset: Asset | null
  groups: AssetGroup[]
  sshKeys: SSHKey[]
  serialPorts: SerialPort[]
  error: string | null
  onChange: (field: keyof AddAssetForm, value: string) => void
  onClose: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

type DeleteAssetModalProps = {
  asset: Asset
  error: string | null
  onClose: () => void
  onDelete: () => Promise<void>
}

function AssetFormModal({ mode, form, assets, targetAsset, groups, sshKeys, serialPorts, error, onChange, onClose, onSubmit }: AssetFormModalProps) {
  const { t } = useAppearance()
  const isUsedAsProxy = targetAsset ? assets.some((a) => a.proxyAssetId === targetAsset.id) : false
  const proxyCandidates = assets.filter((asset) => isProxyCandidate(asset, targetAsset?.id ?? null))
  const proxySelectorDisabled = !supportsSshProxyTarget(form.assetKind) || isUsedAsProxy
  const usesPassword = ['password', 'password_and_key'].includes(form.authType)
  const usesSshKey = ['key', 'password_and_key'].includes(form.authType)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ops-bg/60 backdrop-blur-md animate-in fade-in duration-300" role="presentation">
      <form className="w-[520px] max-w-[90vw] max-h-[90vh] overflow-y-auto bg-ops-panel/90 border border-ops-border/40 rounded-2xl p-8 shadow-2xl flex flex-col gap-6 backdrop-blur-xl animate-in zoom-in-95 duration-300" role="dialog" aria-modal="true" aria-labelledby="add-asset-title" onSubmit={onSubmit}>
        <div className="flex items-center justify-between pb-4 border-b border-ops-border/20">
          <h3 id="add-asset-title" className="text-[16px] font-bold  tracking-[0.15em] text-ops-cyan">
            {mode === 'edit-asset' ? t('assets.updateInfrastructure') : t('assets.newInfrastructure')}
          </h3>
          <button type="button" onClick={onClose} className="text-ops-muted hover:text-ops-text transition-colors">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
            {t('assets.connectionMode')}
            <select className="field-control" value={form.mode} onChange={(event) => onChange('mode', event.target.value as ConnectionMode)}>
              <option value="ssh">{t('assets.sshProtocol')}</option>
              <option value="serial">{t('assets.serialConnection')}</option>
            </select>
          </label>
          {form.mode === 'ssh' ? (
            <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
              {t('assets.environment')}
              <select className="field-control" value={form.assetKind} onChange={(event) => onChange('assetKind', event.target.value as AssetKind)}>
                <option value="linux">{t('assets.linuxServer')}</option>
                <option value="cisco">Cisco IOS</option>
                <option value="huawei">Huawei VRP</option>
                <option value="juniper">Juniper JunOS</option>
                <option value="h3c">H3C Comware</option>
                <option value="network">{t('assets.genericNetwork')}</option>
              </select>
            </label>
          ) : (
            <div className="col-span-2 sm:col-span-1" />
          )}
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
            {t('assets.displayName')}
            <input className="field-control" value={form.name} onChange={(event) => onChange('name', event.target.value)} placeholder={form.mode === 'serial' ? 'serial-dev-01' : 'prod-server-01'} required />
          </label>
          <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
            {t('assets.resourceGroup')}
            <select className="field-control" value={form.groupId} onChange={(event) => onChange('groupId', event.target.value)}>
              <option value="">{t('settings.defaultGroup')}</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>{group.name}</option>
              ))}
            </select>
          </label>
          {form.mode === 'ssh' ? (
            <>
              <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
                {t('assets.endpointHost')}
                <input className="field-control font-mono" value={form.host} onChange={(event) => onChange('host', event.target.value)} placeholder="10.0.0.1" required />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
                {t('assets.port')}
                <input className="field-control font-mono" type="number" min="1" max="65535" value={form.port} onChange={(event) => onChange('port', event.target.value)} placeholder="22" required />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
                {t('assets.systemUser')}
                <input className="field-control font-mono" value={form.username} onChange={(event) => onChange('username', event.target.value)} placeholder="root" required />
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
                {t('assets.authStrategy')}
                <select className="field-control" value={form.authType} onChange={(event) => onChange('authType', event.target.value)}>
                  <option value="password">{t('assets.password')}</option>
                  <option value="key">{t('assets.sshKeypair')}</option>
                  <option value="password_and_key">{t('assets.twoFactor')}</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
                SSH Jump Asset
                <select className="field-control" value={form.proxyAssetId} onChange={(event) => onChange('proxyAssetId', event.target.value)} disabled={proxySelectorDisabled}>
                  <option value="">Direct connection</option>
                  {proxyCandidates.map((asset) => (
                    <option key={asset.id} value={asset.id}>{asset.name}</option>
                  ))}
                </select>
                {proxySelectorDisabled ? (
                  <span className="text-[10px] normal-case tracking-normal text-ops-muted/70">
                    {isUsedAsProxy
                      ? 'This asset is used as a proxy by other assets and cannot use a jump proxy itself.'
                      : 'SSH proxy is supported only for Linux and network device assets in this version.'}
                  </span>
                ) : null}
              </label>
              {usesSshKey ? (
                <label className="flex flex-col gap-2 text-[11px] font-bold  tracking-widest text-ops-muted/70 col-span-2 sm:col-span-1">
                  {t('assets.selectSshKey')}
                  <select className="field-control" value={form.sshKeyId} onChange={(event) => onChange('sshKeyId', event.target.value)} required>
                    <option value="">{t('assets.selectIdentity')}</option>
                    {sshKeys.map((sshKey) => (
                      <option key={sshKey.id} value={sshKey.id}>{sshKey.name}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              {usesPassword ? (
                <label className="flex flex-col gap-2 text-[11px] font-bold tracking-widest text-ops-muted/70 col-span-2">
                  {t('assets.password')}
                  <input className="field-control font-mono" type="password" value={form.credentialSecret} onChange={(event) => onChange('credentialSecret', event.target.value)} placeholder="••••••••••••" required={mode !== 'edit-asset'} />
                </label>
              ) : null}
            </>
          ) : null}
          {form.mode === 'serial' ? (
            <>
              <label className="flex flex-col gap-1 text-sm text-ops-muted col-span-2 sm:col-span-1">
                {t('assets.serialPort')}
                <input className="field-control" list="serial-ports-list" value={form.serialPort} onChange={(event) => onChange('serialPort', event.target.value)} placeholder="COM3 / /dev/ttyUSB0" required />
                <datalist id="serial-ports-list">
                  {serialPorts.map((port) => (
                    <option key={port.device} value={port.device}>
                      {port.description && port.description !== 'n/a' ? `${port.device} (${port.description})` : port.device}
                    </option>
                  ))}
                </datalist>
              </label>
              <label className="flex flex-col gap-1 text-sm text-ops-muted col-span-2 sm:col-span-1">
                {t('assets.baudRate')}
                <input className="field-control" type="number" value={form.baudRate} onChange={(event) => onChange('baudRate', event.target.value)} placeholder="9600" required />
              </label>
              <label className="flex flex-col gap-1 text-sm text-ops-muted col-span-2 sm:col-span-1">
                {t('assets.dataBits')}
                <select className="field-control" value={form.dataBits} onChange={(event) => onChange('dataBits', event.target.value)}>
                  <option value="5">5</option>
                  <option value="6">6</option>
                  <option value="7">7</option>
                  <option value="8">8</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm text-ops-muted col-span-2 sm:col-span-1">
                {t('assets.parity')}
                <select className="field-control" value={form.parity} onChange={(event) => onChange('parity', event.target.value)}>
                  <option value="none">{t('assets.parityNone')}</option>
                  <option value="odd">{t('assets.parityOdd')}</option>
                  <option value="even">{t('assets.parityEven')}</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm text-ops-muted col-span-2 sm:col-span-1">
                {t('assets.stopBits')}
                <select className="field-control" value={form.stopBits} onChange={(event) => onChange('stopBits', event.target.value)}>
                  <option value="1">1</option>
                  <option value="1.5">1.5</option>
                  <option value="2">2</option>
                </select>
              </label>
            </>
          ) : null}
        </div>
        {error ? <div className="settings-error text-center py-2 px-4 bg-ops-danger/10 border border-ops-danger/20 rounded-lg">{error}</div> : null}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-ops-border/20">
          <button type="button" className="button px-6" onClick={onClose}>{t('common.cancel')}</button>
          <button type="submit" className="button button-primary px-8 shadow-glow">{t('assets.authorizeAndSave')}</button>
        </div>
      </form>
    </div>
  )
}

function DeleteAssetModal({ asset, error, onClose, onDelete }: DeleteAssetModalProps) {
  const { t } = useAppearance()

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ops-bg/60 backdrop-blur-md animate-in fade-in duration-300" role="presentation">
      <div className="w-[420px] max-w-[90vw] bg-ops-panel/90 border border-ops-border/40 rounded-2xl p-8 shadow-2xl flex flex-col gap-6 backdrop-blur-xl animate-in zoom-in-95 duration-300" role="dialog" aria-modal="true">
        <div className="flex items-center gap-4 text-ops-danger">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-ops-danger/10">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
          </div>
          <h3 className="text-lg font-bold  tracking-wider">{t('assets.confirmDeletion')}</h3>
        </div>
        <p className="text-[13px] leading-relaxed text-ops-text/80">
          {t('assets.confirmDeleteAsset', { name: asset.name })}
        </p>
        <div className="flex items-center justify-end gap-3 pt-2">
          <button type="button" className="button px-6" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="button button-danger px-8" onClick={() => void onDelete()}>
            {t('assets.decommission')}
          </button>
        </div>
        {error ? <p className="settings-error mt-2">{error}</p> : null}
      </div>
    </div>
  )
}

export const AssetModals = forwardRef<AssetModalsRef, AssetModalsProps>(
  ({ assets, groups, sshKeys, onAddAsset, onUpdateAsset, onDeleteAsset }, ref) => {
    const [activeModal, setActiveModal] = useState<ActiveModal>(null)
    const [targetAsset, setTargetAsset] = useState<Asset | null>(null)
    const [addAssetForm, setAddAssetForm] = useState<AddAssetForm>(emptyAddAssetForm)
    const [addAssetError, setAddAssetError] = useState<string | null>(null)
    const [systemSerialPorts, setSystemSerialPorts] = useState<SerialPort[]>([])

    useEffect(() => {
      if ((activeModal !== 'add-asset' && activeModal !== 'edit-asset') || addAssetForm.mode !== 'serial') {
        return
      }

      const controller = new AbortController()
      getSerialPorts(controller.signal)
        .then(setSystemSerialPorts)
        .catch((error) => {
          if (error instanceof DOMException && error.name === 'AbortError') {
            return
          }
          console.error('Failed to fetch serial ports:', error)
        })

      return () => controller.abort()
    }, [activeModal, addAssetForm.mode])

    const updateAddAssetForm = (field: keyof AddAssetForm, value: string) => {
      setAddAssetForm((currentForm) => {
        const nextForm = { ...currentForm, [field]: value }
        if (field === 'mode' && value !== 'ssh') {
          nextForm.proxyAssetId = ''
        }
        if (field === 'assetKind' && !supportsSshProxyTarget(value as AssetKind)) {
          nextForm.proxyAssetId = ''
        }
        if (field === 'authType') {
          if (value === 'key') {
            nextForm.credentialSecret = ''
          } else if (value === 'password') {
            nextForm.sshKeyId = ''
          }
        }
        return nextForm
      })
    }

    const closeModal = () => {
      setAddAssetForm(emptyAddAssetForm)
      setAddAssetError(null)
      setTargetAsset(null)
      setActiveModal(null)
    }

    const openAddModal = () => {
      setActiveModal('add-asset')
    }

    const openEditModal = (asset: Asset) => {
      if (asset.assetType === 'local_terminal') {
        return
      }
      setTargetAsset(asset)
      const mode: ConnectionMode = asset.assetType === 'serial' ? 'serial' : 'ssh'
      const assetKind: AssetKind = ['linux', 'network', 'cisco', 'huawei', 'juniper', 'h3c'].includes(asset.assetType)
        ? (asset.assetType as AssetKind)
        : 'linux'
      const supportsProxy = supportsSshProxyTarget(assetKind)
      const tagValue = (prefix: string, fallback: string) => asset.tags.find((tag) => tag.startsWith(`${prefix}:`))?.split(':')[1] ?? fallback

      setAddAssetForm({
        mode,
        assetKind: mode === 'serial' ? 'serial' : assetKind,
        name: asset.name,
        host: asset.host,
        port: String(asset.port),
        username: asset.username,
        authType: asset.authType || 'password',
        credentialSecret: '',
        sshKeyId: asset.sshKeyId ? String(asset.sshKeyId) : '',
        proxyAssetId: supportsProxy && asset.proxyAssetId ? String(asset.proxyAssetId) : '',
        serialPort: mode === 'serial' ? asset.host : '',
        baudRate: mode === 'serial' ? String(asset.port) : '9600',
        dataBits: tagValue('data-bits', '8'),
        parity: tagValue('parity', 'none'),
        stopBits: tagValue('stop-bits', '1'),
        groupId: asset.groupId ? String(asset.groupId) : '',
      })
      setActiveModal('edit-asset')
    }

    const openDeleteModal = (asset: Asset) => {
      setTargetAsset(asset)
      setActiveModal('delete-asset')
    }

    useImperativeHandle(ref, () => ({
      openAddModal,
      openEditModal,
      openDeleteModal,
    }))

    const handleAssetSubmit = async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      setAddAssetError(null)
      try {
        const payload = addAssetForm.mode === 'serial'
          ? {
            name: addAssetForm.name,
            asset_type: 'serial' as const,
            group_id: addAssetForm.groupId ? Number(addAssetForm.groupId) : null,
            host: addAssetForm.serialPort.trim(),
            port: Number(addAssetForm.baudRate),
            username: '',
            auth_type: '',
            proxy_asset_id: null,
            tags: buildConnectionTags(addAssetForm),
            vendor: targetAsset?.vendor || '',
            description: targetAsset?.description || '',
          }
          : {
            name: addAssetForm.name,
            asset_type: addAssetForm.assetKind,
            group_id: addAssetForm.groupId ? Number(addAssetForm.groupId) : null,
            host: addAssetForm.host.trim(),
            port: Number(addAssetForm.port),
            username: addAssetForm.username.trim(),
            auth_type: addAssetForm.authType,
            ssh_key_id: ['key', 'password_and_key'].includes(addAssetForm.authType) ? (addAssetForm.sshKeyId ? Number(addAssetForm.sshKeyId) : null) : null,
            proxy_asset_id: supportsSshProxyTarget(addAssetForm.assetKind) && addAssetForm.proxyAssetId ? Number(addAssetForm.proxyAssetId) : null,
            credential_secret: ['password', 'password_and_key'].includes(addAssetForm.authType)
              ? addAssetForm.credentialSecret.trim() || undefined
              : undefined,
            tags: buildConnectionTags(addAssetForm),
            vendor: targetAsset?.vendor || '',
            description: targetAsset?.description || '',
          }

        if (activeModal === 'edit-asset' && targetAsset) {
          await onUpdateAsset(targetAsset.id, payload)
        } else {
          await onAddAsset(payload)
        }
        closeModal()
      } catch (error) {
        setAddAssetError(error instanceof Error ? error.message : 'Failed to save infrastructure')
      }
    }

    const handleAssetDelete = async () => {
      if (!targetAsset) {
        return
      }
      setAddAssetError(null)
      try {
        await onDeleteAsset(targetAsset.id)
        closeModal()
      } catch (error) {
        setAddAssetError(error instanceof Error ? error.message : 'Deletion Failed')
      }
    }

    return (
      <>
        {(activeModal === 'add-asset' || activeModal === 'edit-asset') ? (
          <AssetFormModal
            mode={activeModal}
            form={addAssetForm}
            assets={assets}
            targetAsset={targetAsset}
            groups={groups}
            sshKeys={sshKeys}
            serialPorts={systemSerialPorts}
            error={addAssetError}
            onChange={updateAddAssetForm}
            onClose={closeModal}
            onSubmit={handleAssetSubmit}
          />
        ) : null}

        {activeModal === 'delete-asset' && targetAsset ? (
          <DeleteAssetModal
            asset={targetAsset}
            error={addAssetError}
            onClose={closeModal}
            onDelete={handleAssetDelete}
          />
        ) : null}
      </>
    )
  }
)

AssetModals.displayName = 'AssetModals'
