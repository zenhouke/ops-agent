import { useAppearance } from '../../hooks/useAppearance'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSkillPackages } from '../../hooks/useSkillPackages'
import type { RunMode } from '../../types/api'
import type { Asset, ConversationContextStatus } from '../../types/ops'
import { ModelSelector } from './ModelSelector'

type PromptInputProps = {
  prompt: string
  models: string[]
  selectedModel: string
  runMode: RunMode
  selectedAsset: Asset
  contextStatus: ConversationContextStatus | null
  blockedRun: { message: string; actionLabel: string } | null
  onViewBlockedRun?: () => void
  onOpenSettings?: () => void
  onPromptChange: (prompt: string) => void
  onModelChange: (model: string) => void
  onRunModeChange: (mode: RunMode) => void
  onRun: (prompt: string, selectedSkillName?: string | null) => Promise<void>
}

const MODE_DESCRIPTION_KEY: Record<RunMode, 'assistant.agentDescription' | 'assistant.planDescription'> = {
  agent: 'assistant.agentDescription',
  plan: 'assistant.planDescription',
}

const MODE_LABEL_KEY: Record<RunMode, 'assistant.agent' | 'assistant.plan'> = {
  agent: 'assistant.agent',
  plan: 'assistant.plan',
}

function contextStatusColor(status: ConversationContextStatus | null) {
  if (!status) return 'rgba(148,163,184,0.55)'
  if (status.contextStatus === 'critical') return '#ef4444'
  if (status.contextStatus === 'warning') return '#f59e0b'
  return '#06b6d4'
}

function contextPercent(status: ConversationContextStatus | null) {
  return Math.max(0, Math.min(100, status?.contextPercent ?? 0))
}

function formatTokenCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return `${value}`
}

function contextLabel(status: ConversationContextStatus | null) {
  return status ? `${contextPercent(status)}%` : '--%'
}

function contextUsageLabel(status: ConversationContextStatus | null) {
  if (!status?.tokenUsage) return contextLabel(status)
  return `${contextLabel(status)} · ${formatTokenCount(status.tokenUsage.totalTokens)} tokens`
}

function contextUsageTitle(status: ConversationContextStatus | null) {
  if (!status?.tokenUsage) return contextLabel(status)
  const usage = status.tokenUsage
  return `上下文窗口 ${contextLabel(status)}；本会话真实累计 ${usage.totalTokens} tokens（input ${usage.inputTokens}，output ${usage.outputTokens}，cache read ${usage.cacheReadInputTokens}，cache write ${usage.cacheCreationInputTokens}）`
}

function getSlashSuggestionQuery(prompt: string) {
  const match = prompt.match(/^\s*\/([^\s]*)$/)
  return match ? match[1] : null
}

function parseLeadingSkillCommand(prompt: string, validSkillNames: Set<string>) {
  const trimmedPrompt = prompt.trimStart()
  const match = trimmedPrompt.match(/^\/([^\s/]+)(?=\s|$)/)

  if (!match) {
    return { prompt, selectedSkillName: null as string | null }
  }

  const selectedSkillName = match[1]
  if (!validSkillNames.has(selectedSkillName)) {
    return { prompt, selectedSkillName: null as string | null }
  }

  return {
    prompt: trimmedPrompt.slice(match[0].length).trimStart(),
    selectedSkillName,
  }
}

export function PromptInput({
  prompt,
  models,
  selectedModel,
  runMode,
  selectedAsset,
  contextStatus,
  blockedRun,
  onViewBlockedRun,
  onOpenSettings,
  onPromptChange,
  onModelChange,
  onRunModeChange,
  onRun,
}: PromptInputProps) {
  const { t } = useAppearance()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const { skillPackages, loading: skillsLoading, loadSkillPackages } = useSkillPackages()

  const slashSuggestionQuery = useMemo(() => getSlashSuggestionQuery(prompt), [prompt])
  const shouldShowSlashSuggestions = slashSuggestionQuery !== null
  const modelBlockedRun = models.length === 0 || !selectedModel
    ? { message: '未配置 LLM 模型，请先在设置中添加并设为默认模型。', actionLabel: '' }
    : null
  const effectiveBlockedRun = blockedRun ?? modelBlockedRun

  useEffect(() => {
    if (!shouldShowSlashSuggestions) {
      return
    }

    void loadSkillPackages()
  }, [loadSkillPackages, shouldShowSlashSuggestions])

  const filteredSkillPackages = useMemo(() => {
    if (slashSuggestionQuery === null) {
      return []
    }

    const query = slashSuggestionQuery.toLowerCase()
    return (skillPackages ?? []).filter((skill) => skill.name.toLowerCase().startsWith(query))
  }, [skillPackages, slashSuggestionQuery])

  const selectSkillSuggestion = useCallback((skillName: string) => {
    onPromptChange(`/${skillName} `)
    requestAnimationFrame(() => {
      const textarea = textareaRef.current
      if (!textarea) {
        return
      }
      textarea.focus()
      const cursor = textarea.value.length
      textarea.setSelectionRange(cursor, cursor)
    })
  }, [onPromptChange])

  const submitPrompt = async () => {
    const currentPrompt = prompt

    if (!currentPrompt.trim()) {
      return
    }

    if (effectiveBlockedRun) {
      return
    }

    let nextPrompt = currentPrompt
    let selectedSkillName: string | null = null

    if (/^\s*\//.test(currentPrompt)) {
      const validSkills = await loadSkillPackages()
      const parsedPrompt = parseLeadingSkillCommand(
        currentPrompt,
        new Set(validSkills.map((skill) => skill.name)),
      )
      nextPrompt = parsedPrompt.prompt
      selectedSkillName = parsedPrompt.selectedSkillName
    }

    onPromptChange('')

    try {
      await onRun(nextPrompt, selectedSkillName)
    }
    catch {
      onPromptChange(currentPrompt)
    }
  }

  return (
    <div className="relative mx-5 mb-3 mt-1 shrink-0 rounded-2xl border border-ops-border/20 bg-ops-panel/70 shadow-lg backdrop-blur-xl transition-all duration-300 focus-within:border-ops-green/30 focus-within:shadow-[0_0_24px_rgb(var(--ops-green)/0.08)]">
      <div className="relative overflow-visible rounded-2xl bg-[radial-gradient(circle_at_18%_0%,rgb(var(--ops-green)/0.08),transparent_40%),linear-gradient(180deg,rgb(var(--ops-panel)/0.85),rgb(var(--ops-deep)/0.9))]">
        <div className="relative flex items-center gap-3 border-b border-ops-border/10 px-3 py-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-2" aria-label={t('assistant.context')}>
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ops-green opacity-30" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-ops-green shadow-glow" />
            </span>
            <span className="truncate text-[11px] font-black uppercase tracking-[0.18em] text-ops-green/90">
              {selectedAsset.name}
            </span>
            <span className="hidden truncate rounded-full border border-ops-border/30 bg-ops-deep/70 px-2.5 py-1 font-mono text-[10px] text-ops-muted/70 md:inline">
              {selectedAsset.host || 'local'}
            </span>
          </div>
        
          <span
            className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-full border border-ops-border/25 bg-ops-deep/65 px-2 py-1 font-mono text-[10px] text-ops-muted/75"
            title={contextUsageTitle(contextStatus)}
            aria-label={contextUsageTitle(contextStatus)}
          >
            <span
              aria-hidden="true"
              className="h-3.5 w-3.5 rounded-full"
              style={{
                background: `conic-gradient(${contextStatusColor(contextStatus)} ${contextPercent(contextStatus)}%, rgba(148,163,184,0.22) 0)`,
              }}
            />
            <span>{contextUsageLabel(contextStatus)}</span>
          </span>
        </div>

        <label className="sr-only" htmlFor="prompt-input">
          {t('assistant.commandInput')}
        </label>
        <div className="relative">
          <textarea
            id="prompt-input"
            ref={textareaRef}
            className="min-h-[56px] w-full resize-none bg-transparent px-4 pb-3.5 pr-16 pt-2.5 text-[13px] font-medium leading-relaxed text-ops-text caret-ops-green outline-none placeholder:text-ops-muted/32 scrollbar-thin"
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void submitPrompt()
              }
            }}
            placeholder={t('assistant.promptPlaceholder')}
          />

          <button
            className={`absolute bottom-3 right-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border transition-all duration-200 active:scale-95 ${prompt.trim() && !effectiveBlockedRun
              ? 'border-ops-green/40 bg-ops-green text-ops-deep hover:-translate-y-0.5 hover:bg-ops-green/85 hover:shadow-glow'
              : 'cursor-not-allowed border-ops-border/20 bg-ops-panel/60 text-ops-muted/25'
              }`}
            type="button"
            onClick={() => {
              void submitPrompt()
            }}
            disabled={!prompt.trim() || Boolean(effectiveBlockedRun)}
            aria-label={t('assistant.runMission')}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false" className="h-5 w-5 fill-current"><path d="M5 3.8 20.2 12 5 20.2v-6.1L13.4 12 5 9.9z" /></svg>
          </button>
        </div>

        {effectiveBlockedRun ? (
          <div className="relative flex items-center gap-2 border-t border-ops-warning/15 bg-ops-warning/8 px-3 py-2 text-[11px] font-bold text-ops-warning">
            <span className="min-w-0 flex-1 truncate">{effectiveBlockedRun.message}</span>
            {blockedRun && onViewBlockedRun ? (
              <button
                type="button"
                className="shrink-0 rounded-lg border border-ops-warning/30 px-2.5 py-1 text-[10px] font-black transition hover:bg-ops-warning/10 active:scale-95"
                onClick={onViewBlockedRun}
              >
                {blockedRun.actionLabel}
              </button>
            ) : modelBlockedRun && onOpenSettings ? (
              <button
                type="button"
                className="shrink-0 rounded-lg border border-ops-warning/30 px-2.5 py-1 text-[10px] font-black transition hover:bg-ops-warning/10 active:scale-95"
                onClick={onOpenSettings}
              >
                {t('assistant.openSettings')}
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="relative z-20 flex items-center gap-3 border-t border-ops-border/10 bg-ops-deep/45 px-3 py-2">
          <div className="flex flex-1 items-center gap-3 overflow-visible">
            <ModelSelector models={models} selectedModel={selectedModel} onModelChange={onModelChange} />

            <div className="group flex min-w-fit items-center gap-3">
              <div
                className="inline-flex items-center rounded-full border border-ops-border/20 bg-ops-deep/75 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
                role="radiogroup"
                aria-label={t('assistant.mode')}
              >
                {(Object.keys(MODE_LABEL_KEY) as RunMode[]).map((mode) => {
                  const isActive = runMode === mode
                  return (
                    <button
                      key={mode}
                      type="button"
                      role="radio"
                      aria-checked={isActive}
                      title={t(MODE_DESCRIPTION_KEY[mode])}
                      onClick={() => onRunModeChange(mode)}
                      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] transition-all duration-200 active:scale-95 ${isActive
                        ? 'border-ops-green/30 bg-ops-green/12 text-ops-green'
                        : 'border-transparent text-ops-muted/55 hover:bg-ops-panel/80 hover:text-ops-text'
                        }`}
                    >
                      {mode === 'plan' ? (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"></rect><path d="M7 11V7a5 5 0 0110 0v4"></path></svg>
                      ) : (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><circle cx="12" cy="12" r="3" /><path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.24M15.54 15.54l4.24 4.24M1 12h6M17 12h6M4.22 19.78l4.24-4.24M15.54 8.46l4.24-4.24" /></svg>
                      )}
                      {t(MODE_LABEL_KEY[mode])}
                    </button>
                  )
                })}
              </div>
              <span className="hidden max-w-[280px] truncate text-[10px] font-bold tracking-[0.08em] text-ops-muted/35 transition-all duration-300 group-hover:text-ops-muted/70 lg:inline">
                {t(MODE_DESCRIPTION_KEY[runMode])}
              </span>
            </div>
          </div>
        </div>
      </div>

      {shouldShowSlashSuggestions ? (
        <div
          className="absolute bottom-[calc(100%+0.35rem)] left-4 right-16 z-50 overflow-hidden rounded-xl border border-ops-border/25 bg-ops-deep/95 shadow-xl backdrop-blur-xl"
          role="listbox"
          aria-label={t('assistant.availableSkills')}
        >
          <div className="border-b border-ops-border/10 px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-ops-muted/60">
            {t('assistant.slashSkills')}
          </div>
          <div className="max-h-[420px] overflow-y-auto py-1">
            {skillsLoading ? (
              <div className="px-3.5 py-2.5 text-[12px] text-ops-muted/70">{t('assistant.loadingSkills')}</div>
            ) : filteredSkillPackages.length > 0 ? (
              filteredSkillPackages.map((skill) => (
                <button
                  key={skill.path}
                  type="button"
                  className="flex min-h-[42px] w-full flex-col items-start gap-0.5 px-3.5 py-2 text-left transition-colors hover:bg-ops-green/10 focus:bg-ops-green/10 focus:outline-none"
                  onMouseDown={(event) => {
                    event.preventDefault()
                  }}
                  onClick={() => selectSkillSuggestion(skill.name)}
                  role="option"
                  aria-label={`/${skill.name}`}
                >
                  <span className="font-mono text-[12px] text-ops-green">/{skill.name}</span>
                  <span className="line-clamp-1 text-[10px] leading-4 text-ops-muted/80">{skill.description || t('settings.noDescription')}</span>
                </button>
              ))
            ) : (
              <div className="px-3.5 py-2.5 text-[12px] text-ops-muted/70">{t('assistant.noMatchingSkills')}</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
