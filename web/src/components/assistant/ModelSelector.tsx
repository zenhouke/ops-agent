import { useEffect, useRef, useState } from 'react'
import { useAppearance } from '../../hooks/useAppearance'

type ModelSelectorProps = {
  models: string[]
  selectedModel: string
  onModelChange: (model: string) => void
}

export function ModelSelector({ models, selectedModel, onModelChange }: ModelSelectorProps) {
  const { t } = useAppearance()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const selectedIndex = Math.max(0, models.indexOf(selectedModel))
  const hasModels = models.length > 0

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
        className="group flex w-full items-center gap-2 rounded-full border border-slate-300/70 bg-white/90 px-3 py-1.5 text-left text-[11px] font-semibold tracking-[0.035em] text-slate-700 shadow-[0_8px_22px_rgba(15,23,42,0.08),inset_0_1px_0_rgba(255,255,255,0.85)] outline-none transition-all duration-200 hover:border-cyan-500/40 hover:text-slate-950 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 dark:border-ops-cyan/10 dark:bg-ops-deep/75 dark:text-ops-muted dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] dark:hover:border-ops-cyan/35 dark:hover:text-ops-text dark:focus:border-ops-cyan/65 dark:focus:ring-ops-cyan/15"
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
        <span className={`h-2 w-2 shrink-0 rounded-full ${hasModels ? 'bg-cyan-500 shadow-[0_0_14px_rgba(6,182,212,0.55)] dark:bg-ops-cyan' : 'bg-ops-warning/80'}`} />
        <span className="min-w-0 flex-1 truncate">{hasModels ? selectedModel || t('settings.undefined') : '未配置模型'}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200 dark:text-ops-muted/70 ${open ? 'rotate-180' : ''}`}
        >
          <path fill="currentColor" d="M5.2 7.4 10 12.1l4.8-4.7 1.1 1.2-5.9 5.8-5.9-5.8z" />
        </svg>
      </button>

      {open ? (
        <div className="absolute bottom-[calc(100%+0.45rem)] left-0 z-50 w-[min(340px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-slate-200/80 bg-white/95 p-1.5 shadow-[0_18px_55px_rgba(15,23,42,0.18)] backdrop-blur-xl dark:border-ops-cyan/15 dark:bg-ops-deep/95 dark:shadow-[0_18px_60px_rgba(0,0,0,0.45)]">
          <div className="border-b border-slate-200/80 px-3 py-1.5 text-[9px] font-black uppercase tracking-[0.18em] text-slate-400 dark:border-ops-border/12 dark:text-ops-muted/50">
            {t('assistant.modelSelector')}
          </div>
          <div className="max-h-64 overflow-y-auto py-1" role="listbox" aria-label={t('assistant.modelSelector')}>
            {hasModels ? models.map((model) => {
              const active = model === selectedModel
              return (
                <button
                  key={model}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-[11px] font-semibold tracking-[0.025em] transition-all duration-150 ${active
                    ? 'bg-cyan-50 text-cyan-700 shadow-[inset_3px_0_0_rgba(6,182,212,0.75)] dark:bg-ops-cyan/12 dark:text-ops-cyan dark:shadow-[inset_3px_0_0_rgb(var(--ops-cyan))]'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-ops-muted/75 dark:hover:bg-ops-panel/80 dark:hover:text-ops-text'
                    }`}
                  onClick={() => selectModel(model)}
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${active ? 'bg-cyan-500 dark:bg-ops-cyan' : 'bg-slate-300 dark:bg-ops-border'}`} />
                  <span className="min-w-0 flex-1 truncate">{model}</span>
                </button>
              )
            }) : (
              <div className="px-3 py-2 text-[11px] font-semibold text-ops-warning/85">
                未配置 LLM 模型
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
