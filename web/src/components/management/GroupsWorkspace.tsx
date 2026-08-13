import { type FormEvent, useState } from 'react'
import { createGroup, deleteGroup, updateGroup } from '../../api'
import { useAppearance } from '../../hooks/useAppearance'
import type { AssetGroup } from '../../types/ops'
import { DeleteConfirmDialog } from '../settings/DeleteConfirmDialog'
import { GroupsSection } from '../settings/GroupsSection'
import type { GroupForm } from '../settings/settingsTypes'
import { ManagementShell } from './ManagementShell'

const emptyGroupForm: GroupForm = { name: '', description: '' }

export function GroupsWorkspace({ groups, onGroupsChange }: { groups: AssetGroup[]; onGroupsChange: (groups: AssetGroup[]) => void }) {
  const { t } = useAppearance()
  const [groupForm, setGroupForm] = useState(emptyGroupForm)
  const [showGroupForm, setShowGroupForm] = useState(false)
  const [editingGroup, setEditingGroup] = useState<AssetGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<AssetGroup | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resetForm = () => {
    setEditingGroup(null)
    setShowGroupForm(false)
    setGroupForm(emptyGroupForm)
  }

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = { name: groupForm.name.trim(), description: groupForm.description.trim() }
      const saved = editingGroup ? await updateGroup(editingGroup.id, payload) : await createGroup(payload)
      onGroupsChange(editingGroup ? groups.map((group) => group.id === saved.id ? saved : group) : [saved, ...groups])
      resetForm()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('management.groupsSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deletingGroup) return
    setSaving(true)
    setError(null)
    try {
      await deleteGroup(deletingGroup.id)
      onGroupsChange(groups.filter((group) => group.id !== deletingGroup.id))
      setDeletingGroup(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('management.groupsDeleteFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <ManagementShell title={t('management.groups')} description={t('management.groupsDescription')}>
      {error ? <div className="mb-4 border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger">{error}</div> : null}
      <GroupsSection
        groups={groups}
        groupForm={groupForm}
        showGroupForm={showGroupForm}
        saving={saving}
        onFormChange={setGroupForm}
        onCancelForm={resetForm}
        onSave={saveGroup}
        onStartDelete={setDeletingGroup}
        onStartCreate={() => {
          setEditingGroup(null)
          setDeletingGroup(null)
          setGroupForm(emptyGroupForm)
          setShowGroupForm(true)
        }}
        onStartEdit={(group) => {
          setEditingGroup(group)
          setDeletingGroup(null)
          setGroupForm({ name: group.name, description: group.description })
          setShowGroupForm(true)
        }}
      />
      {deletingGroup ? (
        <DeleteConfirmDialog
          titleId="delete-group-title"
          title={t('settings.confirmGroupDeletion')}
          message={deletingGroup.name}
          saving={saving}
          onCancel={() => setDeletingGroup(null)}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </ManagementShell>
  )
}
