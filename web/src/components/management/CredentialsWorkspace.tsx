import { type FormEvent, useEffect, useState } from 'react'
import { createSSHKey, deleteSSHKey, getSSHKeys, updateSSHKey } from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import type { SSHKey } from '../../types/ops'
import { DeleteConfirmDialog } from '../settings/DeleteConfirmDialog'
import { SSHKeysSection } from '../settings/SSHKeysSection'
import type { SSHKeyForm } from '../settings/settingsTypes'
import { ManagementShell } from './ManagementShell'

type CredentialsWorkspaceProps = {
  initialSSHKeys: SSHKey[]
  onSSHKeysChange: (sshKeys: SSHKey[]) => void
}

const emptySSHKeyForm: SSHKeyForm = { name: '', publicKey: '', privateKey: '', passphrase: '' }

export function CredentialsWorkspace({ initialSSHKeys, onSSHKeysChange }: CredentialsWorkspaceProps) {
  const { t } = useAppearance()
  const [sshKeys, setSSHKeys] = useState(initialSSHKeys)
  const [sshKeyForm, setSSHKeyForm] = useState(emptySSHKeyForm)
  const [showSSHKeyForm, setShowSSHKeyForm] = useState(false)
  const [editingSSHKey, setEditingSSHKey] = useState<SSHKey | null>(null)
  const [deletingSSHKey, setDeletingSSHKey] = useState<SSHKey | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void getSSHKeys()
      .then((next) => {
        if (!active) return
        setSSHKeys(next)
        onSSHKeysChange(next)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : t('management.credentialsLoadFailed'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [t])

  const resetForm = () => {
    setEditingSSHKey(null)
    setShowSSHKeyForm(false)
    setSSHKeyForm(emptySSHKeyForm)
  }

  const saveSSHKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: sshKeyForm.name.trim(),
        public_key: sshKeyForm.publicKey.trim(),
        private_key: sshKeyForm.privateKey.trim() || undefined,
        passphrase: sshKeyForm.passphrase.trim() || undefined,
      }
      const saved = editingSSHKey
        ? await updateSSHKey(editingSSHKey.id, payload)
        : await createSSHKey({ ...payload, private_key: sshKeyForm.privateKey.trim() })
      const next = editingSSHKey
        ? sshKeys.map((key) => key.id === saved.id ? saved : key)
        : [saved, ...sshKeys]
      setSSHKeys(next)
      onSSHKeysChange(next)
      resetForm()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('management.credentialsSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deletingSSHKey) return
    setSaving(true)
    setError(null)
    try {
      await deleteSSHKey(deletingSSHKey.id)
      const next = sshKeys.filter((key) => key.id !== deletingSSHKey.id)
      setSSHKeys(next)
      onSSHKeysChange(next)
      setDeletingSSHKey(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('management.credentialsDeleteFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <ManagementShell title={t('management.credentials')} description={t('management.credentialsDescription')}>
      {error ? <div className="mb-4 border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger">{error}</div> : null}
      {loading ? (
        <div className="py-16 text-center text-xs text-ops-muted">{t('settings.loading')}</div>
      ) : (
        <SSHKeysSection
          sshKeys={sshKeys}
          sshKeyForm={sshKeyForm}
          showSSHKeyForm={showSSHKeyForm}
          editingSSHKey={editingSSHKey}
          saving={saving}
          onFormChange={setSSHKeyForm}
          onCancelForm={resetForm}
          onSave={saveSSHKey}
          onStartDelete={setDeletingSSHKey}
          onStartCreate={() => {
            setEditingSSHKey(null)
            setDeletingSSHKey(null)
            setSSHKeyForm(emptySSHKeyForm)
            setShowSSHKeyForm(true)
          }}
          onStartEdit={(key) => {
            setEditingSSHKey(key)
            setDeletingSSHKey(null)
            setSSHKeyForm({ name: key.name, publicKey: key.publicKey, privateKey: '', passphrase: '' })
            setShowSSHKeyForm(true)
          }}
        />
      )}
      {deletingSSHKey ? (
        <DeleteConfirmDialog
          titleId="delete-ssh-key-title"
          title={t('settings.confirmSshKeyDeletion')}
          message={deletingSSHKey.name}
          saving={saving}
          onCancel={() => setDeletingSSHKey(null)}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </ManagementShell>
  )
}
