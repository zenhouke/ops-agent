import { useEffect, useState } from 'react'
import { getKnowledgeVersion, getKnowledgeVersions, restoreKnowledgeVersion, type KnowledgeVersion, type KnowledgeVersionPreview } from '../../api/knowledge'

type Props = { entryId: string; updatedAt: string; onRestored: () => Promise<unknown> }

export function KnowledgeVersionHistory({ entryId, updatedAt, onRestored }: Props) {
  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState<KnowledgeVersion[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [preview, setPreview] = useState<{ versionId: string; content: KnowledgeVersionPreview } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const selected = preview?.versionId === selectedId ? preview.content : null

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    void getKnowledgeVersions(entryId).then((items) => { if (active) setVersions(items) })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : '读取历史版本失败') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [entryId, updatedAt, open, revision])

  useEffect(() => {
    if (!selectedId || !open) return
    let active = true
    setPreview(null)
    setError(null)
    void getKnowledgeVersion(entryId, selectedId).then((content) => { if (active) setPreview({ versionId: selectedId, content }) })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : '读取版本差异失败') })
    return () => { active = false }
  }, [entryId, selectedId, updatedAt, open, revision])

  const restore = async () => {
    if (!selected || saving) return
    setSaving(true)
    setError(null)
    try {
      await restoreKnowledgeVersion(entryId, selectedId, selected.currentUpdatedAt)
      setSelectedId('')
      setPreview(null)
      setNotice('已恢复，恢复前的内容也已保留为历史版本。')
      await onRestored()
      setRevision((value) => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '恢复失败，请刷新版本后重试')
    } finally { setSaving(false) }
  }

  return <section className="mb-5 border-b border-ops-border/25 pb-4" aria-label="知识版本历史">
    <button type="button" className="flex w-full items-center justify-between text-xs font-semibold text-ops-text" aria-expanded={open} onClick={() => setOpen(!open)}><span>版本历史</span><span>{open ? '收起' : '查看'}</span></button>
    {notice ? <p role="status" className="mt-2 text-[11px] text-ops-green">{notice}</p> : null}
    {open ? <div className="mt-3 space-y-3">
      {error ? <p role="alert" className="break-words text-xs text-ops-danger">{error}<button type="button" className="ml-2 underline" disabled={saving} onClick={() => setRevision((value) => value + 1)}>刷新</button></p> : null}
      <select aria-label="选择历史版本" className="field-control w-full text-xs" value={selectedId} disabled={loading || saving} onChange={(event) => setSelectedId(event.target.value)}><option value="">{loading ? '正在加载…' : versions.length ? '选择版本查看差异' : '暂无历史版本'}</option>{versions.map((version) => <option key={version.id} value={version.id}>{new Date(version.updatedAt).toLocaleString('zh-CN')}</option>)}</select>
      {!loading && versions.length === 0 ? <p className="text-[11px] text-ops-muted">更新文件前会自动保存旧版本。</p> : null}
      {selectedId && !selected && !error ? <p className="text-[11px] text-ops-muted">正在对比内容…</p> : null}
      {selected ? <><p className="text-[11px] text-ops-muted">对比当前版本：红色为将移除的内容，绿色为将恢复的内容。</p><pre className="max-h-80 overflow-auto rounded bg-ops-bg p-2 text-[10px] leading-5" aria-label="版本差异">{selected.diff ? selected.diff.split('\n').map((line, index) => <span key={index} className={`block whitespace-pre-wrap break-all ${line.startsWith('+') ? 'text-ops-green' : line.startsWith('-') ? 'text-ops-danger' : 'text-ops-muted'}`}>{line || ' '}</span>) : '内容一致'}</pre><button type="button" className="button w-full px-2 py-2 text-xs" disabled={saving} onClick={() => void restore()}>{saving ? '正在恢复…' : '恢复此版本'}</button><p className="text-[10px] text-ops-muted">恢复前会保存当前版本，可再次撤销。</p></> : null}
    </div> : null}
  </section>
}
