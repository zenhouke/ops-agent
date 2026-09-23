import { useEffect, useRef, useState } from 'react'
import { getAvailableModels } from '../../api/modelConfigs'
import { useAppearance } from '../../hooks/useAppearance'

type ModelSelectorProps = {
  models: string[]
  selectedModel: string
  onModelChange: (model: string) => void
}

export function ModelSelector({ selectedModel, onModelChange }: ModelSelectorProps) {
  const { t } = useAppearance()
  const [open, setOpen] = useState(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [revision, setRevision] = useState(0)
  const models = availableModels.filter((model) => model.toLowerCase().includes(query.toLowerCase()))
  useEffect(() => {
    const changed = () => { setAvailableModels([]); setRevision((value) => value + 1) }
    window.addEventListener('ops-agent:model-service-changed', changed)
    return () => window.removeEventListener('ops-agent:model-service-changed', changed)
  }, [])
  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    setAvailableModels([])
    void getAvailableModels().then((items) => {
      if (active) setAvailableModels(items)
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : '获取模型列表失败')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [open, revision])

  const rootRef = useRef<HTMLDivElement | null>(null)
  const selectedIndex = Math.max(0, models.indexOf(selectedModel))

  useEffect(() => {
    if (!open) {
      return
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    window.addEventListener('pointerdown', handlePointerDown)
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [open])

  const selectModel = (model: string) => {
    onModelChange(model)
    setOpen(false)
  }

  const moveSelection = (direction: 1 | -1) => {
    if (models.length === 0) {
      return
    }
    const nextIndex = (selectedIndex + direction + models.length) % models.length
    onModelChange(models[nextIndex])
  }

  return (
    <div ref={rootRef} className="relative min-w-[180px] max-w-[260px] shrink-0 font-mono">
      <label className="sr-only" htmlFor="model-selector-button">
        {t('assistant.modelSelector')}
      </label>
      <button
        id="model-selector-button"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        className="group flex w-full items-center gap-2 rounded-full border border-ops-border/55 bg-ops-panel/90 px-3 py-1.5 text-left text-[11px] font-semibold tracking-[0.035em] text-ops-muted shadow-[0_8px_22px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.45)] outline-none transition-all duration-200 hover:border-ops-cyan/40 hover:text-ops-text focus:border-ops-cyan/65 focus:ring-2 focus:ring-ops-cyan/15 dark:bg-ops-deep/75 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            if (!open) {
              setOpen(true)
              return
            }
            moveSelection(1)
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault()
            if (!open) {
              setOpen(true)
              return
            }
            moveSelection(-1)
          }
          if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      >
        <span className="h-2 w-2 shrink-0 rounded-full bg-ops-cyan shadow-[0_0_10px_rgb(var(--ops-cyan)/0.24)]" />
        <span className="min-w-0 flex-1 truncate">{selectedModel || '选择模型'}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className={`h-4 w-4 shrink-0 text-ops-muted/70 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        >
          <path fill="currentColor" d="M5.2 7.4 10 12.1l4.8-4.7 1.1 1.2-5.9 5.8-5.9-5.8z" />
        </svg>
      </button>

      {open ? (
        <div className="absolute bottom-[calc(100%+0.45rem)] right-0 z-50 w-[min(340px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-ops-border/65 bg-ops-panel/95 p-1.5 shadow-[0_18px_55px_rgba(0,0,0,0.18)] backdrop-blur-xl dark:border-ops-cyan/15 dark:bg-ops-deep/95 dark:shadow-[0_18px_60px_rgba(0,0,0,0.45)]">
          <div className="border-b border-ops-border/40 px-3 py-1.5 text-[9px] font-black uppercase tracking-[0.18em] text-ops-muted/60">
            {t('assistant.modelSelector')}
          </div>
          <div className="flex gap-2 px-2 py-2">
            <input className="field-control min-w-0 flex-1 text-xs" aria-label="搜索模型" placeholder="搜索服务提供的模型" value={query} onChange={(event) => setQuery(event.target.value)} />
            <button type="button" className="button-mini" disabled={loading} onClick={() => setRevision((value) => value + 1)}>刷新</button>
          </div>
          {loading ? <p role="status" className="px-3 py-2 text-xs text-ops-muted">正在获取模型列表…</p> : null}
          {error ? <p role="alert" className="px-3 py-2 text-xs text-ops-danger">{error}</p> : null}
          {!loading && !error && !models.length ? <p role="status" className="px-3 py-2 text-xs text-ops-muted">{availableModels.length ? '没有匹配的模型' : '服务未返回可用模型，请检查模型服务配置。'}</p> : null}
          <div className="max-h-64 overflow-y-auto py-1" role="listbox" aria-label={t('assistant.modelSelector')}>
            {models.map((model) => {
              const active = model === selectedModel
              return (
                <button
                  key={model}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-[11px] font-semibold tracking-[0.025em] transition-all duration-150 ${active
                    ? 'bg-ops-cyan/[0.12] text-ops-cyan shadow-[inset_3px_0_0_rgb(var(--ops-cyan))]'
                    : 'text-ops-muted/75 hover:bg-ops-strong/65 hover:text-ops-text'
                    }`}
                  onClick={() => selectModel(model)}
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${active ? 'bg-ops-cyan' : 'bg-ops-border'}`} />
                  <span className="min-w-0 flex-1 truncate">{model}</span>
                </button>
              )
            })}
          </div>
        </div>
      ) : null}
    </div>
  )
}
