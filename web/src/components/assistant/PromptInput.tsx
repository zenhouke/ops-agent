import { useAppearance } from '../../hooks/useAppearance'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSkillPackages } from '../../hooks/useSkillPackages'
import type { BackgroundRunStatus } from '../../hooks/console/agentRunSupport'
import type { Asset, ConversationContextStatus } from '../../types/ops'
import { ModelSelector } from './ModelSelector'

type PromptInputProps = {
  prompt: string
  models: string[]
  selectedModel: string
  selectedAsset: Asset
  contextStatus: ConversationContextStatus | null
  blockedRun: { message: string; actionLabel: string } | null
  onViewBlockedRun?: () => void
  onPromptChange: (prompt: string) => void
  onModelChange: (model: string) => void
  onRun: (prompt: string, selectedSkillName?: string | null, mode?: 'standard' | 'incident') => Promise<void>
  runStatus: BackgroundRunStatus | null
  isRunning: boolean
  onCancel: () => Promise<void>
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
  if (status.tokenUsage.measurement === 'unavailable') return `${contextLabel(status)} · tokens --`
  return `${contextLabel(status)} · ${formatTokenCount(status.tokenUsage.totalTokens)} tokens`
}

function contextUsageTitle(status: ConversationContextStatus | null) {
  if (!status?.tokenUsage) return contextLabel(status)
  const usage = status.tokenUsage
  if (usage.measurement === 'unavailable') {
    return `上下文窗口 ${contextLabel(status)}；当前模型没有返回可核验的 token 用量`
  }
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

function activePromptCopy(status: BackgroundRunStatus | null) {
  if (status === 'needs_input') {
    return { placeholder: '回复 Agent 的问题…', sendLabel: '回复 Agent', sendTitle: '回复后 Agent 将继续当前任务' }
  }
  if (status === 'needs_approval') {
    return { placeholder: '补充审批说明；批准或拒绝仍需在审批卡操作…', sendLabel: '补充说明', sendTitle: '只补充说明，不会批准或执行命令' }
  }
  if (status === 'disconnected') {
    return { placeholder: '连接已中断；可向后台任务补充指令…', sendLabel: '补充指令', sendTitle: '发送到仍在后台运行的 Agent' }
  }
  return { placeholder: '补充条件或纠正 Agent 当前方向…', sendLabel: '补充指令', sendTitle: '发送到当前 Agent 运行' }
}

export function PromptInput({
  prompt,
  models,
  selectedModel,
  selectedAsset,
  contextStatus,
  blockedRun,
  onViewBlockedRun,
  onPromptChange,
  onModelChange,
  onRun,
  runStatus,
  isRunning,
  onCancel,
}: PromptInputProps) {
  const { t } = useAppearance()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const { skillPackages, loading: skillsLoading, loadSkillPackages } = useSkillPackages()
  const [incidentMode, setIncidentMode] = useState(false)
  const runningCopy = activePromptCopy(runStatus)

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
      await onRun(nextPrompt, selectedSkillName, incidentMode ? 'incident' : 'standard')
    }
    catch {
      onPromptChange(currentPrompt)
    }
  }

  return (
    <div className="relative mx-auto mb-2 mt-1 w-[calc(100%-2.5rem)] max-w-[980px] shrink-0 rounded-[18px] border border-ops-border/35 bg-ops-panel/80 shadow-[0_10px_32px_rgb(var(--ops-bg)/0.28)] transition-all duration-200 focus-within:border-ops-text/35 focus-within:ring-1 focus-within:ring-ops-text/10">
      <div className="relative overflow-visible rounded-[17px]">
        <label className="sr-only" htmlFor="prompt-input">
          {t('assistant.commandInput')}
        </label>
        <div className="relative">
          <textarea
            id="prompt-input"
            ref={textareaRef}
            className={`min-h-[58px] w-full resize-none bg-transparent px-4 pb-2 pt-3.5 text-[13px] font-medium leading-relaxed text-ops-text caret-ops-text outline-none placeholder:text-ops-muted/35 scrollbar-thin ${isRunning ? 'pr-28' : 'pr-20'}`}
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void submitPrompt()
              }
            }}
            placeholder={isRunning ? runningCopy.placeholder : t('assistant.promptPlaceholder')}
          />

          <button
            className={`absolute bottom-2 right-3 flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-full border px-3 text-[10px] font-bold transition-all duration-200 active:scale-95 ${prompt.trim() && !blockedRun
              ? 'border-ops-text bg-ops-text text-ops-bg hover:bg-ops-text/85'
              : 'cursor-not-allowed border-ops-border/20 bg-ops-panel/70 text-ops-muted/25'
              }`}
            type="button"
            onClick={() => void submitPrompt()}
            disabled={!prompt.trim() || Boolean(blockedRun)}
            aria-label={isRunning ? runningCopy.sendLabel : t('assistant.runMission')}
            title={isRunning ? runningCopy.sendTitle : undefined}
          >
            <span>{isRunning ? runningCopy.sendLabel : '发送'}</span>
            <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false" className="h-3.5 w-3.5 fill-none stroke-current" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5" /><path d="m6.5 10.5 5.5-5.5 5.5 5.5" /></svg>
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

        <div className="relative z-20 flex items-center gap-2 px-3 pb-2.5 pt-0.5">
          <div className="flex min-w-0 flex-1 items-center gap-2 overflow-visible">
            <div className="flex min-w-0 items-center gap-1.5 rounded-full px-1.5 py-1" aria-label={t('assistant.context')}>
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ops-green" />
              <span className="max-w-[150px] truncate text-[9px] font-semibold text-ops-text/75">{selectedAsset.name}</span>
              <span className="hidden max-w-[120px] truncate font-mono text-[9px] text-ops-muted/45 lg:inline">{selectedAsset.host || '本地'}</span>
            </div>
            <button
              type="button"
              className={`shrink-0 rounded border px-2 py-1 text-[9px] font-semibold transition ${incidentMode ? 'border-ops-danger/40 bg-ops-danger/10 text-ops-danger' : 'border-ops-border/25 text-ops-muted/60 hover:text-ops-text'}`}
              aria-pressed={incidentMode}
              title="启用事故响应框架；不会绕过命令审批"
              onClick={() => setIncidentMode((current) => !current)}
            >
              事故模式
            </button>
            {isRunning ? (
              <button
                className="inline-flex shrink-0 items-center gap-1.5 rounded border border-ops-danger/30 bg-ops-danger/[0.06] px-2 py-1 text-[9px] font-semibold text-ops-danger transition hover:bg-ops-danger/[0.12] active:scale-95"
                type="button"
                onClick={() => void onCancel()}
                aria-label="停止当前 Agent 运行"
                title="停止当前 Agent 运行"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false" className="h-2.5 w-2.5 fill-current"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
                停止
              </button>
            ) : null}
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
