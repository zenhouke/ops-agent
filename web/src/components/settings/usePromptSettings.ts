import { useCallback, useEffect, useState } from 'react'
import { getPromptSettings, resetPromptSettings, updatePromptSettings } from '../../api'
import type { PromptOverrides, PromptSettings } from '../../api'

export function usePromptSettings() {
  const [settings, setSettings] = useState<PromptSettings | null>(null)
  const [overrides, setOverrides] = useState<PromptOverrides | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const next = await getPromptSettings()
      setSettings(next)
      setOverrides(next.overrides)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to load prompt settings.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const save = useCallback(async () => {
    if (!settings || !overrides) return
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const next = await updatePromptSettings(settings.revision, overrides)
      setSettings(next)
      setOverrides(next.overrides)
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to save prompt settings.')
    } finally {
      setSaving(false)
    }
  }, [overrides, settings])

  const reset = useCallback(async () => {
    if (!settings) return
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const next = await resetPromptSettings(settings.revision)
      setSettings(next)
      setOverrides(next.overrides)
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to reset prompt settings.')
    } finally {
      setSaving(false)
    }
  }, [settings])

  return { settings, overrides, setOverrides, loading, saving, error, saved, load, save, reset }
}
