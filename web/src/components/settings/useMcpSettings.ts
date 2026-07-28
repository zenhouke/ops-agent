import { type FormEvent, useCallback, useEffect, useState } from 'react'

import {
  createMCPServer,
  deleteMCPServer,
  listMCPServers,
  refreshMCPServer,
  setMCPServerEnabled,
  testMCPServer,
  updateMCPServer,
  updateMCPTool,
} from '../../api'
import type { MCPServer, MCPTool } from '../../types/ops'
import type { MCPServerForm } from './settingsTypes'

const emptyServerForm: MCPServerForm = {
  name: '',
  transport: 'stdio',
  command: '',
  args: '',
  env: '{}',
  url: '',
  headers: '{}',
  timeoutSeconds: '30',
}

function toForm(server: MCPServer): MCPServerForm {
  return {
    name: server.name,
    transport: server.transport,
    command: server.command,
    args: server.args.join('\n'),
    env: JSON.stringify(server.env, null, 2),
    url: server.url,
    headers: JSON.stringify(server.headers, null, 2),
    timeoutSeconds: String(server.timeoutSeconds),
  }
}

function parseRecord(value: string, label: string) {
  const trimmed = value.trim()
  if (!trimmed) return {}
  const parsed: unknown = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return Object.fromEntries(
    Object.entries(parsed).map(([key, entry]) => [key, String(entry)]),
  )
}

export function useMcpSettings() {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [serverForm, setServerForm] = useState<MCPServerForm>(emptyServerForm)
  const [showServerForm, setShowServerForm] = useState(false)
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null)
  const [deletingServer, setDeletingServer] = useState<MCPServer | null>(null)
  const [selectedServerId, setSelectedServerId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const next = await listMCPServers()
      setServers(next)
      setSelectedServerId((current) => current ?? next[0]?.id ?? null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load MCP servers')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runSaving = async (action: () => Promise<void>, fallback: string) => {
    setSaving(true)
    setError(null)
    try {
      await action()
    } catch (operationError) {
      setError(operationError instanceof Error ? operationError.message : fallback)
    } finally {
      setSaving(false)
    }
  }

  const updateInList = (server: MCPServer) => {
    setServers((current) => current.map((item) => item.id === server.id ? server : item))
    setSelectedServerId(server.id)
  }

  const resetForm = () => {
    setEditingServer(null)
    setShowServerForm(false)
    setTestResult(null)
    setServerForm(emptyServerForm)
  }

  const startCreate = () => {
    resetForm()
    setDeletingServer(null)
    setShowServerForm(true)
  }

  const startEdit = (server: MCPServer) => {
    setEditingServer(server)
    setDeletingServer(null)
    setTestResult(null)
    setServerForm(toForm(server))
    setShowServerForm(true)
    setSelectedServerId(server.id)
  }

  const createPayload = () => ({
    name: serverForm.name.trim(),
    transport: serverForm.transport,
    command: serverForm.transport === 'stdio' ? serverForm.command.trim() : '',
    args: serverForm.transport === 'stdio'
      ? serverForm.args.split('\n').map((arg) => arg.trim()).filter(Boolean)
      : [],
    env: serverForm.transport === 'stdio' ? parseRecord(serverForm.env, 'Env') : {},
    url: serverForm.transport === 'httpSse' ? serverForm.url.trim() : '',
    headers: serverForm.transport === 'httpSse'
      ? parseRecord(serverForm.headers, 'Headers')
      : {},
    timeoutSeconds: Number(serverForm.timeoutSeconds) || 30,
  })

  const updatePayload = (server: MCPServer) => {
    const original = toForm(server)
    const transportChanged = server.transport !== serverForm.transport
    return {
      name: serverForm.name.trim(),
      transport: serverForm.transport,
      command: serverForm.transport === 'stdio' ? serverForm.command.trim() : '',
      args: serverForm.transport === 'stdio'
        ? serverForm.args.split('\n').map((arg) => arg.trim()).filter(Boolean)
        : [],
      url: serverForm.transport === 'httpSse' ? serverForm.url.trim() : '',
      timeoutSeconds: Number(serverForm.timeoutSeconds) || 30,
      ...(serverForm.transport !== 'stdio'
        ? { env: {} }
        : transportChanged || serverForm.env !== original.env
          ? { env: parseRecord(serverForm.env, 'Env') }
          : {}),
      ...(serverForm.transport !== 'httpSse'
        ? { headers: {} }
        : transportChanged || serverForm.headers !== original.headers
          ? { headers: parseRecord(serverForm.headers, 'Headers') }
          : {}),
    }
  }

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await runSaving(async () => {
      const saved = editingServer
        ? await updateMCPServer(editingServer.id, updatePayload(editingServer))
        : await createMCPServer(createPayload())
      setServers((current) => editingServer
        ? current.map((server) => server.id === saved.id ? saved : server)
        : [saved, ...current])
      setSelectedServerId(saved.id)
      resetForm()
    }, 'Failed to save MCP server')
  }

  const confirmDelete = async () => {
    if (!deletingServer) return
    await runSaving(async () => {
      await deleteMCPServer(deletingServer.id)
      const next = servers.filter((server) => server.id !== deletingServer.id)
      setServers(next)
      setSelectedServerId((current) => current === deletingServer.id
        ? next[0]?.id ?? null
        : current)
      setDeletingServer(null)
    }, 'Failed to delete MCP server')
  }

  const test = async (server: MCPServer) => {
    setTestResult(null)
    await runSaving(async () => {
      const result = await testMCPServer(server.id)
      if (result.server) updateInList(result.server)
      setTestResult(result.message)
    }, 'MCP server test failed')
  }

  const refresh = async (server: MCPServer) => {
    await runSaving(async () => {
      updateInList(await refreshMCPServer(server.id))
    }, 'Failed to refresh MCP server')
  }

  const setEnabled = async (server: MCPServer, enabled: boolean) => {
    await runSaving(async () => {
      updateInList(await setMCPServerEnabled(server.id, enabled))
    }, 'Failed to update MCP server')
  }

  const updateTool = async (
    tool: MCPTool,
    updates: { enabled?: boolean; approvalPolicy?: 'allow' | 'ask' | 'deny' },
  ) => {
    await runSaving(async () => {
      updateInList(await updateMCPTool(tool.id, updates))
    }, 'Failed to update MCP tool')
  }

  return {
    servers,
    serverForm,
    setServerForm,
    showServerForm,
    editingServer,
    deletingServer,
    setDeletingServer,
    selectedServerId,
    setSelectedServerId,
    testResult,
    loading,
    saving,
    error,
    load,
    startCreate,
    startEdit,
    resetForm,
    save,
    confirmDelete,
    test,
    refresh,
    setEnabled,
    updateTool,
  }
}
