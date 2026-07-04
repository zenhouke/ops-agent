import { useEffect, useMemo, useState } from 'react'
import type {
  KnowledgeDraft,
  KnowledgeEntry,
  KnowledgeEntryPayload,
  KnowledgeGenerateDraftResponse,
  KnowledgeSourceConversation,
} from '../../types/ops'

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

type DraftFormState = {
  title: string
  summary: string
  problem: string
  diagnosis: string
  resolution: string
  tags: string
}

const EMPTY_FORM: DraftFormState = {
  title: '',
  summary: '',
  problem: '',
  diagnosis: '',
  resolution: '',
  tags: '',
}

function formFromDraft(draft: KnowledgeDraft | null): DraftFormState {
  if (!draft) {
    return EMPTY_FORM
  }

  return {
    title: draft.title,
    summary: draft.summary,
    problem: draft.problem,
    diagnosis: draft.diagnosis,
    resolution: draft.resolution,
    tags: draft.tags.join(', '),
  }
}

function parseTags(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function compactText(value: string, fallback: string) {
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : fallback
}

export function KnowledgeDraftReview({
  conversationId,
  selectedModel,
  draft,
  draftSourceConversation,
  draftLoading,
  draftError,
  saving,
  onGenerateDraft,
  onSaveDraft,
  onClearDraft,
}: KnowledgeDraftReviewProps) {
  const [expanded, setExpanded] = useState(false)
  const [form, setForm] = useState<DraftFormState>(() => formFromDraft(draft))

  useEffect(() => {
    setForm(formFromDraft(draft))
    setExpanded(Boolean(draft))
  }, [draft])

  const disabled = draftLoading || saving
  const hasDraft = Boolean(draft)
  const draftTitle = compactText(form.title, '未命名知识草稿')
  const sourceTitle = compactText(draftSourceConversation?.title ?? '', '当前会话')

  const commandSummaries = useMemo(() => draft?.commands ?? [], [draft])
  const assetSummaries = useMemo(() => draft?.assets ?? [], [draft])
  const sourceSummaries = useMemo(() => draft?.sources ?? [], [draft])

  const handleGenerate = () => {
    if (!conversationId || disabled) {
      return
    }

    void onGenerateDraft(conversationId, { modelName: selectedModel || null })
  }

  const handleFieldChange = (field: keyof DraftFormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const handleSave = () => {
    if (!draft || disabled) {
      return
    }

    void onSaveDraft({
      title: form.title,
      summary: form.summary,
      problem: form.problem,
      diagnosis: form.diagnosis,
      resolution: form.resolution,
      tags: parseTags(form.tags),
    })
  }

  return (
    <section className="relative z-10 mx-4 mt-4 rounded-2xl border border-ops-border/20 bg-ops-panel/55 shadow-2xl shadow-black/10 backdrop-blur">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-ops-green/25 bg-ops-green/10 text-ops-green">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v18" /><path d="M5 8h14" /><path d="M5 16h14" /></svg>
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] font-black uppercase tracking-[0.16em] text-ops-muted/70">知识草稿</span>
            <span className="block truncate text-sm font-black text-ops-text">{hasDraft ? draftTitle : '生成知识草稿'}</span>
          </span>
          {hasDraft ? <span className="hidden rounded-full border border-ops-border/20 px-2 py-1 text-[10px] font-bold text-ops-muted sm:inline">{sourceTitle}</span> : null}
        </button>

        {!hasDraft ? (
          <button
            type="button"
            className="shrink-0 rounded-xl border border-ops-green/30 bg-ops-green/10 px-3 py-2 text-[10px] font-black tracking-[0.08em] text-ops-green transition hover:bg-ops-green/20 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
            disabled={!conversationId || disabled}
            onClick={handleGenerate}
          >
            {draftLoading ? '生成中' : '生成知识草稿'}
          </button>
        ) : (
          <button
            type="button"
            className="shrink-0 rounded-xl border border-ops-border/20 px-3 py-2 text-[10px] font-black text-ops-muted transition hover:border-ops-green/40 hover:text-ops-green active:scale-95"
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded ? '收起' : '展开'}
          </button>
        )}
      </div>

      {draftError ? (
        <div className="mx-4 mb-3 rounded-xl border border-ops-danger/35 bg-ops-danger/10 px-3 py-2 text-xs font-bold text-ops-danger" role="alert">
          {draftError}
        </div>
      ) : null}

      {expanded && draft ? (
        <div className="space-y-4 border-t border-ops-border/15 px-4 py-4">
          {draft.redactionWarnings.length > 0 ? (
            <div className="rounded-xl border border-ops-warning/35 bg-ops-warning/10 px-3 py-2 text-xs text-ops-warning">
              <div className="mb-1 font-black">脱敏提醒</div>
              <ul className="list-disc space-y-1 pl-4">
                {draft.redactionWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="grid gap-3 lg:grid-cols-2">
            <label className="lg:col-span-2">
              <span className="mb-1 block text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/70">标题</span>
              <input
                className="w-full rounded-xl border border-ops-border/20 bg-ops-bg/70 px-3 py-2 text-sm font-bold text-ops-text outline-none transition focus:border-ops-green/50"
                value={form.title}
                disabled={disabled}
                onChange={(event) => handleFieldChange('title', event.target.value)}
              />
            </label>

            <DraftTextarea label="摘要" value={form.summary} disabled={disabled} onChange={(value) => handleFieldChange('summary', value)} />
            <DraftTextarea label="问题" value={form.problem} disabled={disabled} onChange={(value) => handleFieldChange('problem', value)} />
            <DraftTextarea label="诊断" value={form.diagnosis} disabled={disabled} onChange={(value) => handleFieldChange('diagnosis', value)} />
            <DraftTextarea label="处置" value={form.resolution} disabled={disabled} onChange={(value) => handleFieldChange('resolution', value)} />

            <label className="lg:col-span-2">
              <span className="mb-1 block text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/70">标签</span>
              <input
                className="w-full rounded-xl border border-ops-border/20 bg-ops-bg/70 px-3 py-2 text-sm text-ops-text outline-none transition focus:border-ops-green/50"
                value={form.tags}
                disabled={disabled}
                placeholder="tag-a, tag-b"
                onChange={(event) => handleFieldChange('tags', event.target.value)}
              />
            </label>
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <ReadOnlySummary title="命令" emptyText="无命令摘要" items={commandSummaries.map((item) => compactText(item.command, '未命名命令'))} />
            <ReadOnlySummary title="资产" emptyText="无资产摘要" items={assetSummaries.map((item) => compactText(item.label, '未命名资产'))} />
            <ReadOnlySummary title="来源" emptyText="无来源摘要" items={sourceSummaries.map((item) => item.eventIndex !== null ? `事件 #${item.eventIndex}` : compactText(item.relevance, '会话来源'))} />
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-ops-border/15 pt-3">
            <button
              type="button"
              className="rounded-xl border border-ops-border/20 px-3 py-2 text-[10px] font-black text-ops-muted transition hover:border-ops-danger/40 hover:text-ops-danger active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
              disabled={disabled}
              onClick={onClearDraft}
            >
              清除
            </button>
            <button
              type="button"
              className="rounded-xl border border-ops-emerald/30 bg-ops-emerald/10 px-4 py-2 text-[10px] font-black tracking-[0.08em] text-ops-emerald transition hover:bg-ops-emerald/20 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
              disabled={disabled}
              onClick={handleSave}
            >
              {saving ? '保存中' : '保存知识'}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}

type DraftTextareaProps = {
  label: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
}

function DraftTextarea({ label, value, disabled, onChange }: DraftTextareaProps) {
  return (
    <label>
      <span className="mb-1 block text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/70">{label}</span>
      <textarea
        className="min-h-24 w-full resize-y rounded-xl border border-ops-border/20 bg-ops-bg/70 px-3 py-2 text-sm text-ops-text outline-none transition focus:border-ops-green/50"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

type ReadOnlySummaryProps = {
  title: string
  emptyText: string
  items: string[]
}

function ReadOnlySummary({ title, emptyText, items }: ReadOnlySummaryProps) {
  return (
    <div className="rounded-xl border border-ops-border/15 bg-ops-bg/45 p-3">
      <div className="mb-2 text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/70">{title}</div>
      {items.length > 0 ? (
        <ul className="space-y-1 text-xs text-ops-muted">
          {items.slice(0, 5).map((item, index) => (
            <li key={`${title}-${index}`} className="truncate">{item}</li>
          ))}
          {items.length > 5 ? <li className="font-bold text-ops-muted/60">另有 {items.length - 5} 项</li> : null}
        </ul>
      ) : (
        <p className="text-xs font-bold text-ops-muted/50">{emptyText}</p>
      )}
    </div>
  )
}
