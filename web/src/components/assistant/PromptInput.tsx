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
  onPromptChange: (prompt: string) => void
  onModelChange: (model: string) => void
  onRunModeChange: (mode: RunMode) => void
  onRun: (prompt: string, selectedSkillName?: string | null) => Promise<void>
  isRunning: boolean
  onCancel: () => Promise<void>
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
  onPromptChange,
  onModelChange,
  onRunModeChange,
  onRun,
  isRunning,
  onCancel,
}: PromptInputProps) {
  const { t } = useAppearance()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const { skillPackages, loading: skillsLoading, loadSkillPackages } = useSkillPackages()

  const slashSuggestionQuery = useMemo(() => getSlashSuggestionQuery(prompt), [prompt])
  const shouldShowSlashSuggestions = slashSuggestionQuery !== null

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

    if (blockedRun) {
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
    <div className="relative mx-auto mb-2 mt-1 w-[calc(100%-2.5rem)] max-w-[980px] shrink-0 rounded-[5px] border border-ops-border/35 bg-ops-deep shadow-[0_8px_24px_rgb(var(--ops-bg)/0.3)] transition-all duration-200 focus-within:border-ops-cyan/45 focus-within:ring-1 focus-within:ring-ops-cyan/20">
      <div className="relative overflow-visible rounded-[5px] bg-ops-panel/80">
        <label className="sr-only" htmlFor="prompt-input">
          {t('assistant.commandInput')}
        </label>
        <div className="relative">
          <textarea
            id="prompt-input"
            ref={textareaRef}
            className="min-h-[44px] w-full resize-none bg-transparent px-3 pb-2.5 pr-14 pt-2.5 text-[12px] font-medium leading-relaxed text-ops-text caret-ops-cyan outline-none placeholder:text-ops-muted/35 scrollbar-thin"
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
            className={`absolute bottom-2 right-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-[4px] border transition-all duration-200 active:scale-95 ${isRunning
              ? 'border-ops-danger/45 bg-ops-danger text-white hover:bg-ops-danger/85'
              : prompt.trim() && !blockedRun
              ? 'border-ops-cyan/45 bg-ops-cyan text-ops-deep hover:bg-cyan-300'
              : 'cursor-not-allowed border-ops-border/20 bg-ops-panel/70 text-ops-muted/25'
              }`}
            type="button"
            onClick={() => {
              void (isRunning ? onCancel() : submitPrompt())
            }}
            disabled={!isRunning && (!prompt.trim() || Boolean(blockedRun))}
            aria-label={t(isRunning ? 'common.cancel' : 'assistant.runMission')}
          >
            {isRunning ? (
              <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false" className="h-4 w-4 fill-current"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
            ) : (
              <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false" className="h-5 w-5 fill-current"><path d="M5 3.8 20.2 12 5 20.2v-6.1L13.4 12 5 9.9z" /></svg>
            )}
          </button>
        </div>

        {blockedRun ? (
          <div className="relative flex items-center gap-2 border-t border-ops-warning/15 bg-ops-warning/8 px-3 py-2 text-[11px] font-bold text-ops-warning">
            <span className="min-w-0 flex-1 truncate">{blockedRun.message}</span>
            {onViewBlockedRun ? (
              <button
                type="button"
                className="shrink-0 rounded-lg border border-ops-warning/30 px-2.5 py-1 text-[10px] font-black transition hover:bg-ops-warning/10 active:scale-95"
                onClick={onViewBlockedRun}
              >
                {blockedRun.actionLabel}
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="relative z-20 flex items-center gap-2 border-t border-ops-border/20 bg-ops-deep/55 px-2.5 py-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-visible">
            <div className="flex min-w-0 items-center gap-1.5 border-r border-ops-border/20 pr-2" aria-label={t('assistant.context')}>
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ops-green" />
              <span className="max-w-[150px] truncate text-[9px] font-semibold text-ops-text/75">{selectedAsset.name}</span>
              <span className="hidden max-w-[120px] truncate font-mono text-[9px] text-ops-muted/45 lg:inline">{selectedAsset.host || '本地'}</span>
            </div>

            <div className="flex min-w-fit items-center">
              <div
                className="inline-flex items-center rounded-[5px] border border-ops-border/25 bg-ops-deep/75 p-0.5"
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
                      className={`inline-flex items-center gap-1.5 rounded-[4px] border px-2.5 py-1 text-[9px] font-semibold tracking-[0.06em] transition-all duration-200 active:scale-95 ${isActive
                        ? mode === 'agent'
                          ? 'border-ops-cyan/35 bg-ops-cyan/16 text-ops-cyan shadow-[0_0_18px_rgba(6,182,212,0.16)]'
                          : 'border-ops-green/35 bg-ops-green/15 text-ops-green shadow-[0_0_18px_rgba(16,185,129,0.14)]'
                        : 'border-transparent text-ops-muted/55 hover:bg-ops-panel/80 hover:text-ops-text'
                        }`}
                    >
                      {mode === 'plan' ? (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"></rect><path d="M7 11V7a5 5 0 0110 0v4"></path></svg>
                      ) : (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><circle cx="12" cy="12" r="3" /><path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.24M15.54 15.54l4.24 4.24M1 12h6M17 12h6M4.22 19.78l4.24-4.24M15.54 8.46l4.24-4.24" /></svg>
                      )}
                      {mode === 'agent' ? '执行' : t(MODE_LABEL_KEY[mode])}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          <span
            className="inline-flex shrink-0 items-center gap-1.5 rounded-[4px] px-1.5 py-0.5 font-mono text-[9px] text-ops-muted/60"
            title={contextUsageTitle(contextStatus)}
            aria-label={contextUsageTitle(contextStatus)}
          >
            <span
              aria-hidden="true"
              className="h-3 w-3 rounded-full"
              style={{
                background: `conic-gradient(${contextStatusColor(contextStatus)} ${contextPercent(contextStatus)}%, rgba(148,163,184,0.22) 0)`,
              }}
            />
            <span>{contextUsageLabel(contextStatus)}</span>
          </span>
          <ModelSelector models={models} selectedModel={selectedModel} onModelChange={onModelChange} />
        </div>
      </div>

      {shouldShowSlashSuggestions ? (
        <div
          className="absolute bottom-[calc(100%+0.35rem)] left-3 right-14 z-50 overflow-hidden rounded-md border border-ops-cyan/20 bg-ops-deep/95 shadow-[0_18px_60px_rgba(0,0,0,0.45)] backdrop-blur-xl"
          role="listbox"
          aria-label={t('assistant.availableSkills')}
        >
          <div className="border-b border-ops-border/10 px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-ops-muted/65">
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
                  className="flex min-h-[42px] w-full flex-col items-start gap-0.5 px-3.5 py-2 text-left transition-colors hover:bg-ops-cyan/10 focus:bg-ops-cyan/10 focus:outline-none"
                  onMouseDown={(event) => {
                    event.preventDefault()
                  }}
                  onClick={() => selectSkillSuggestion(skill.name)}
                  role="option"
                  aria-label={`/${skill.name}`}
                >
                  <span className="font-mono text-[12px] text-ops-cyan">/{skill.name}</span>
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
