import { useCallback, useEffect, useRef, useState } from 'react'
import { listOperations, type Operation, type OperationKind } from '../api/operations'

export function useOperations(kind: OperationKind, instanceId?: number, organization?: string) {
  const [operations, setOperations] = useState<Operation[]>([])
  const [error, setError] = useState('')
  const generation = useRef(0)
  const refresh = useCallback(async () => {
    const version = generation.current
    try {
      const rows = await listOperations(kind, instanceId, organization)
      if (version === generation.current) { setOperations(rows); setError('') }
    } catch (reason) { if (version === generation.current) setError(reason instanceof Error ? reason.message : String(reason)) }
  }, [kind, instanceId, organization])
  useEffect(() => {
    ++generation.current
    setOperations([])
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => { await refresh(); if (active) timer = setTimeout(() => void poll(), 2000) }
    void poll()
    return () => { active = false; clearTimeout(timer); ++generation.current }
  }, [refresh])
  return { operations, error, refresh }
}
