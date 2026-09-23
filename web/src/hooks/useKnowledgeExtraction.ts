import { useCallback, useEffect, useRef, useState } from 'react'
import { getKnowledgeExtraction, startKnowledgeExtraction, type KnowledgeExtractionJob } from '../api/knowledge'
import type { KnowledgeEntry } from '../types/ops'

export function useKnowledgeExtraction(conversationId: string | null) {
  const [state, setState] = useState<{ conversationId: string | null; job: KnowledgeExtractionJob | null; entries: KnowledgeEntry[] }>({ conversationId: null, job: null, entries: [] })
  const [error, setError] = useState<{ conversationId: string; message: string } | null>(null)
  const [submittingId, setSubmittingId] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const submitting = useRef(new Set<string>())
  const current = state.conversationId === conversationId ? state : null

  useEffect(() => {
    const changed = (event: Event) => {
      if ((event as CustomEvent<{ conversationId: string }>).detail?.conversationId === conversationId) setRevision((value) => value + 1)
    }
    window.addEventListener('ops-agent:knowledge-extraction-changed', changed)
    return () => window.removeEventListener('ops-agent:knowledge-extraction-changed', changed)
  }, [conversationId])

  useEffect(() => {
    if (!conversationId) return
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const result = await getKnowledgeExtraction(conversationId)
        if (!active) return
        setState({ conversationId, ...result })
        setError(null)
        if (result.job?.status === 'queued' || result.job?.status === 'running') timer = setTimeout(() => void poll(), 2000)
      } catch (reason) {
        if (!active) return
        setError({ conversationId, message: reason instanceof Error ? reason.message : '读取提炼状态失败，正在重试' })
        timer = setTimeout(() => void poll(), 5000)
      }
    }
    void poll()
    return () => { active = false; if (timer) clearTimeout(timer) }
  }, [conversationId, revision])

  const start = useCallback(async (modelName: string | null) => {
    if (!conversationId || submitting.current.has(conversationId)) return
    submitting.current.add(conversationId)
    setSubmittingId(conversationId)
    setError(null)
    try {
      const job = await startKnowledgeExtraction(conversationId, modelName)
      setState((previous) => ({ conversationId, job, entries: previous.conversationId === conversationId ? previous.entries : [] }))
      window.dispatchEvent(new CustomEvent('ops-agent:knowledge-extraction-changed', { detail: { conversationId } }))
    } catch (reason) {
      setError({ conversationId, message: reason instanceof Error ? reason.message : '提交后台提炼失败' })
    } finally {
      submitting.current.delete(conversationId)
      setSubmittingId((previous) => previous === conversationId ? null : previous)
    }
  }, [conversationId])

  const job = current?.job
  const busy = submittingId === conversationId && conversationId !== null || job?.status === 'queued' || job?.status === 'running'
  const message = error?.conversationId === conversationId ? error?.message
    : busy ? `${job?.progress || '正在提交后台提炼…'} 可继续对话或切换会话。`
    : job?.status === 'failed' ? `${job.error ?? '提炼失败'} ${job.progress}`
    : job?.status === 'succeeded' && job.total_batches === 0 ? job.progress
    : job?.status === 'succeeded' ? `提炼完成：新增 ${job.created_ids.length} 份，更新 ${job.updated_ids.length} 份，无需变更 ${job.kept_ids.length} 份。`
    : null
  return { start, busy, message, completionKey: job?.status === 'succeeded' ? job.id : null, entries: current?.entries ?? [], failed: job?.status === 'failed' || error?.conversationId === conversationId }
}
