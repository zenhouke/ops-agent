import { useEffect, useMemo, useState } from 'react'
import type { KnowledgeDraft, KnowledgeEntry, KnowledgeEntryPayload, KnowledgeGenerateDraftResponse, KnowledgeSourceConversation } from '../../types/ops'

type KnowledgeDraftReviewProps = {
  conversationId: string | null
  selectedModel: string
  draft: KnowledgeDraft | null
  draftSourceConversation: KnowledgeSourceConversation | null
  draftLoading: boolean
  draftError: string | null
  saving: boolean
  onGenerateDraft: (conversationId: string, payload?: { maxSourceEvents?: number; modelName?: string | null }) => Promise<KnowledgeGenerateDraftResponse | null>
  onSaveDraft: (payload?: Partial<KnowledgeEntryPayload>) => Promise<KnowledgeEntry | null>
  onClearDraft: () => void
  onDraftChange: (draft: KnowledgeDraft | null) => void
}

type DraftFormState = { title: string; summary: string; problem: string; diagnosis: string; resolution: string; tags: string }
const EMPTY_FORM: DraftFormState = { title: '', summary: '', problem: '', diagnosis: '', resolution: '', tags: '' }

function formFromDraft(draft: KnowledgeDraft | null): DraftFormState {
  return draft ? { title: draft.title, summary: draft.summary, problem: draft.problem, diagnosis: draft.diagnosis, resolution: draft.resolution, tags: draft.tags.join(', ') } : EMPTY_FORM
}

function compactText(value: string, fallback: string) {
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : fallback
}

export function KnowledgeDraftReview({ conversationId, selectedModel, draft, draftSourceConversation, draftLoading, draftError, saving, onGenerateDraft, onSaveDraft, onClearDraft }: KnowledgeDraftReviewProps) {
  const [form, setForm] = useState<DraftFormState>(() => formFromDraft(draft))
  useEffect(() => setForm(formFromDraft(draft)), [draft])

  const disabled = draftLoading || saving
  const commandSummaries = useMemo(() => draft?.commands ?? [], [draft])
  const assetSummaries = useMemo(() => draft?.assets ?? [], [draft])
  const sourceSummaries = useMemo(() => draft?.sources ?? [], [draft])
  const handleFieldChange = (field: keyof DraftFormState, value: string) => setForm((current) => ({ ...current, [field]: value }))

  if (!draft) {
    return (
      <section className="flex min-h-[520px] flex-col items-center justify-center text-center" aria-label="从任务提炼知识">
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md border border-ops-border/35 text-ops-muted" aria-hidden="true">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v18M5 8h14M5 16h14" /></svg>
        </div>
        <h2 className="text-sm font-semibold text-ops-text">从当前任务提炼知识</h2>
        <p className="mt-2 max-w-[440px] text-[11px] leading-5 text-ops-muted/70">
          系统会根据任务事件生成可审核草稿。确认保存后，重要信息会同步写入后端 Markdown 文件；生成草稿时不会自动落盘。
        </p>
        <div className="mt-4 flex items-center gap-2 text-[10px] text-ops-muted/55">
          <span>当前任务</span><span>·</span><span>{conversationId ? compactText(draftSourceConversation?.title ?? '', '已选择') : '未选择'}</span><span>·</span><span>{selectedModel || '未选择模型'}</span>
        </div>
        <button type="button" className="button button-primary mt-6 h-9 px-5" disabled={!conversationId || disabled} onClick={() => { if (conversationId) void onGenerateDraft(conversationId, { modelName: selectedModel || null }) }}>
          {draftLoading ? '正在生成草稿' : '生成可审核草稿'}
        </button>
        {!conversationId ? <p className="mt-3 text-[10px] text-ops-warning">请先选择或创建一个任务。</p> : null}
        {draftError ? <div className="mt-4 border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger" role="alert">{draftError}</div> : null}
      </section>
    )
  }

  return (
    <section aria-label="审核知识草稿">
      <div className="flex items-center justify-between border-b border-ops-border/25 pb-4">
        <div>
          <h2 className="text-[13px] font-semibold text-ops-text">审核知识草稿</h2>
          <p className="mt-1 text-[10px] text-ops-muted/65">来源：{compactText(draftSourceConversation?.title ?? '', '当前任务')} · 保存前请确认不包含敏感信息</p>
        </div>
        <button type="button" className="button h-8 px-3" disabled={disabled} onClick={onClearDraft}>放弃草稿</button>
      </div>

      {draftError ? <div className="my-4 border border-ops-danger/30 bg-ops-danger/5 px-3 py-2 text-xs text-ops-danger" role="alert">{draftError}</div> : null}
      {draft.redactionWarnings.length > 0 ? (
        <div className="my-4 border border-ops-warning/30 bg-ops-warning/5 px-3 py-2 text-xs text-ops-warning"><div className="mb-1 font-semibold">脱敏提醒</div>{draft.redactionWarnings.join('；')}</div>
      ) : null}

      <div className="grid gap-4 py-5 lg:grid-cols-2">
        <DraftField className="lg:col-span-2" label="标题" value={form.title} disabled={disabled} onChange={(value) => handleFieldChange('title', value)} />
        <DraftArea label="摘要" value={form.summary} disabled={disabled} onChange={(value) => handleFieldChange('summary', value)} />
        <DraftArea label="问题" value={form.problem} disabled={disabled} onChange={(value) => handleFieldChange('problem', value)} />
        <DraftArea label="诊断" value={form.diagnosis} disabled={disabled} onChange={(value) => handleFieldChange('diagnosis', value)} />
        <DraftArea label="处置" value={form.resolution} disabled={disabled} onChange={(value) => handleFieldChange('resolution', value)} />
        <DraftField className="lg:col-span-2" label="标签" value={form.tags} disabled={disabled} placeholder="例如：ssh, nginx, 故障排查" onChange={(value) => handleFieldChange('tags', value)} />
      </div>

      <div className="grid gap-px overflow-hidden border border-ops-border/25 bg-ops-border/20 lg:grid-cols-3">
        <ReadOnlySummary title="相关命令" emptyText="无命令摘要" items={commandSummaries.map((item) => compactText(item.command, '未命名命令'))} />
        <ReadOnlySummary title="相关资产" emptyText="无资产摘要" items={assetSummaries.map((item) => compactText(item.label, '未命名资产'))} />
        <ReadOnlySummary title="证据来源" emptyText="无来源摘要" items={sourceSummaries.map((item) => item.eventIndex !== null ? `事件 #${item.eventIndex}` : compactText(item.relevance, '任务来源'))} />
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-ops-border/25 pt-4">
        <p className="text-[10px] text-ops-muted/60">保存后将生成 Markdown 文件并进入全局知识检索，可供后续任务引用。</p>
        <button type="button" className="button button-primary h-9 px-5" disabled={disabled} onClick={() => void onSaveDraft({
          title: form.title,
          summary: form.summary,
          problem: form.problem,
          diagnosis: form.diagnosis,
          resolution: form.resolution,
          tags: form.tags.split(',').map((item) => item.trim()).filter(Boolean),
        })}>{saving ? '保存中' : '审核并保存'}</button>
      </div>
    </section>
  )
}

function DraftField({ label, value, disabled, placeholder, className = '', onChange }: { label: string; value: string; disabled: boolean; placeholder?: string; className?: string; onChange: (value: string) => void }) {
  return <label className={className}><span className="mb-1.5 block text-[10px] font-semibold text-ops-muted/70">{label}</span><input className="field-control" value={value} disabled={disabled} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>
}

function DraftArea({ label, value, disabled, onChange }: { label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return <label><span className="mb-1.5 block text-[10px] font-semibold text-ops-muted/70">{label}</span><textarea className="field-control min-h-28 resize-y" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>
}

function ReadOnlySummary({ title, emptyText, items }: { title: string; emptyText: string; items: string[] }) {
  return <div className="min-h-24 bg-ops-deep/45 p-3"><div className="mb-2 text-[9px] font-semibold tracking-[0.08em] text-ops-muted/55">{title}</div>{items.length > 0 ? <ul className="space-y-1 text-[10px] text-ops-muted">{items.slice(0, 5).map((item, index) => <li key={`${title}-${index}`} className="truncate">{item}</li>)}</ul> : <p className="text-[10px] text-ops-muted/45">{emptyText}</p>}</div>
}
