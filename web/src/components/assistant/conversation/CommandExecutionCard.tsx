import { useState, useEffect } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import type { AgentMessage } from '../../../types/ops'
import type { Approval, CommandStart, CommandChunk, CommandEnd } from './types'
import { OutputBlock } from './OutputBlock'

type TerminalToolOutput =
  | {
      tool: 'list_assets'
      status: string
      assets?: Array<{
        asset_id?: number
        assetId?: number
        name?: string
        asset_type?: string
        assetType?: string
        tags?: string[]
        connectable?: boolean
      }>
    }
  | {
      tool: 'request_terminal_session'
      status: string
      requestId?: string
      assetId?: number
      assetName?: string
      reason?: string
      message?: string
    }

function parseTerminalToolOutput(output: string): TerminalToolOutput | null {
  if (!output.trim()) return null
  try {
    const parsed = JSON.parse(output) as TerminalToolOutput
    if (parsed?.tool === 'list_assets' || parsed?.tool === 'request_terminal_session') return parsed
  } catch {
    return null
  }
  return null
}

function StructuredTerminalToolOutput({ output }: { output: TerminalToolOutput }) {
  if (output.tool === 'list_assets') {
    const assets = output.assets ?? []
    return (
      <div className="rounded-[4px] border border-ops-cyan/20 bg-ops-deep/70 p-2.5 shadow-inner">
        <div className="mb-2 flex items-center justify-between gap-3 border-b border-ops-border/20 pb-2">
          <span className="text-[9px] font-bold tracking-[0.1em] text-ops-cyan/85">Visible assets</span>
          <span className="rounded-[4px] border border-ops-cyan/25 bg-ops-cyan/10 px-1.5 py-0.5 text-[9px] font-bold tracking-[0.08em] text-ops-cyan">{assets.length} found</span>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {assets.map((asset) => {
            const assetId = asset.asset_id ?? asset.assetId
            const assetType = asset.asset_type ?? asset.assetType ?? 'asset'
            return (
              <div key={`${assetId ?? asset.name}`} className="rounded-[4px] border border-ops-border/20 bg-ops-panel/35 px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[12px] font-bold text-ops-text/88">{asset.name || `asset-${assetId ?? ''}`}</span>
                  <span className="shrink-0 rounded-[3px] border border-ops-border/25 bg-ops-deep/60 px-1.5 py-0.5 text-[9px] font-bold tracking-[0.08em] text-ops-muted/70">{assetType}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-ops-muted/62">
                  {assetId !== undefined ? <span className="font-mono">id:{assetId}</span> : null}
                  {asset.connectable !== undefined ? <span>{asset.connectable ? 'connectable' : 'unavailable'}</span> : null}
                  {(asset.tags ?? []).slice(0, 3).map((tag) => <span key={tag} className="rounded-[3px] bg-ops-deep/70 px-1.5 py-0.5">{tag}</span>)}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  const isError = output.status === 'error'
  return (
    <div className={`rounded-[4px] border p-2.5 shadow-inner ${isError ? 'border-ops-danger/30 bg-ops-danger/8' : 'border-ops-warning/30 bg-ops-warning/8'}`}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className={`text-[9px] font-black uppercase tracking-[0.16em] ${isError ? 'text-ops-danger' : 'text-ops-warning'}`}>Terminal request</span>
        <span className={`rounded-[4px] border px-1.5 py-0.5 text-[9px] font-bold tracking-[0.08em] ${isError ? 'border-ops-danger/30 text-ops-danger' : 'border-ops-warning/30 text-ops-warning'}`}>{output.status.replace(/_/g, ' ')}</span>
      </div>
      {output.assetName ? <div className="text-[12px] font-bold text-ops-text/88">{output.assetName}</div> : null}
      {output.reason ? <p className="mt-1 m-0 whitespace-pre-wrap text-[11px] leading-relaxed text-ops-muted/72">{output.reason}</p> : null}
      {output.message ? <p className="mt-1 m-0 whitespace-pre-wrap text-[11px] leading-relaxed text-ops-muted/72">{output.message}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10px] text-ops-muted/58">
        {output.assetId !== undefined ? <span>asset:{output.assetId}</span> : null}
        {output.requestId ? <span>request:{output.requestId.slice(0, 8)}</span> : null}
      </div>
    </div>
  )
}

type CommandExecutionCardProps = {
  message?: AgentMessage
  approvalEvent?: Approval
  startEvent?: CommandStart
  chunkEvents?: CommandChunk[]
  endEvent?: CommandEnd
  pendingApprovalRuntimeId: string | null
  onApprove?: (allowPrefix?: string) => void
  onReject?: () => void
}

export function CommandExecutionCard({
  message,
  approvalEvent,
  startEvent,
  chunkEvents = [],
  endEvent,
  pendingApprovalRuntimeId,
  onApprove,
  onReject
}: CommandExecutionCardProps) {
  const { t } = useAppearance()
  const [isExpanded, setIsExpanded] = useState(false)
  const [showWhitelistOptions, setShowWhitelistOptions] = useState(false)
  const [allowPrefix, setAllowPrefix] = useState('')

  // Derived state from AgentMessage or Legacy events
  const toolCall = message?.toolCall
  const rawCommand = toolCall?.command || (startEvent as any)?.command || approvalEvent?.command || ''
  const isCommandTool = Boolean(rawCommand)
  const toolName = toolCall?.name || toolCall?.originalName || ''
  const toolDisplayText = toolCall?.displayText || ''
  const toolDescription = toolCall?.description || ''
  const argsJson = toolCall?.args ? JSON.stringify(toolCall.args, null, 2) : '{}'
  const args = toolCall?.args ?? {}
  const targetAssetName = typeof args.asset_name === 'string' ? args.asset_name : undefined
  const targetTerminalId = typeof args.terminal_id === 'string' ? args.terminal_id : ((startEvent as any)?.terminalId ?? (startEvent as any)?.terminal_id)
  const targetLabel = [targetAssetName, targetTerminalId ? `terminal ${String(targetTerminalId).slice(0, 8)}` : undefined]
    .filter(Boolean)
    .join(' · ')

  // Parse command: if it's JSON like {"command":"lshw -short"}, extract the actual command
  const displayCommand = (() => {
    if (!rawCommand) return ''

    // Try to parse as JSON
    try {
      const parsed = JSON.parse(rawCommand)
      if (parsed && typeof parsed === 'object' && 'command' in parsed) {
        // It's a JSON object with a command field
        return parsed.command
      }
    } catch {
      // Not JSON, use as-is
    }

    return rawCommand
  })()
  const toolSummary = isCommandTool
    ? displayCommand
    : (toolDisplayText || toolDescription || toolName ? [toolDisplayText || toolName, toolDescription].filter(Boolean).join(' — ') : '')

  const outputText = message?.toolOutput ?? chunkEvents.map((event) => event.text).join('')
  const structuredOutput = parseTerminalToolOutput(outputText)
  const exitCode = message ? message.exitCode : ((endEvent as any)?.exitCode ?? (endEvent as any)?.exit_code)
  const hasExecutionResult = message ? message.type === 'say' && message.say === 'tool_use' && !message.partial : !!endEvent
  const commandTokens = displayCommand.trim().split(/\s+/).filter(Boolean)
  const allowPrefixOptions = Array.from(new Set([displayCommand.trim(), commandTokens[0]].filter(Boolean)))
  
  const isMessageAsk = message?.type === 'ask'
  const approvalStatus = isMessageAsk ? 'pending' : (message?.type === 'say' && message?.say === 'tool_use' && !message.partial ? 'approved' : (approvalEvent?.status ?? (approvalEvent ? 'pending' : undefined)))
  
  // For ask-type messages: show buttons when pendingApprovalRuntimeId is set (stream guarantees correctness)
  // For legacy approval events: match on runtimeId
  const showApprovalActions = pendingApprovalRuntimeId !== null && (
    isMessageAsk || 
    (approvalStatus === 'pending' && approvalEvent?.runtimeId === pendingApprovalRuntimeId)
  )

  const isRunning = message ? message.partial : (!endEvent && !approvalStatus)

  useEffect(() => {
    if (showApprovalActions && approvalStatus === 'pending') {
      setIsExpanded(true)
    }
  }, [showApprovalActions, approvalStatus])

  return (
    <div className={`group/card my-1.5 overflow-hidden rounded-[5px] border bg-ops-panel/30 shadow-inner transition-all duration-200 ${approvalStatus === 'pending' ? 'border-ops-warning/35' : 'border-ops-border/30'} ${isExpanded ? 'p-3' : 'px-2.5 py-2'}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-[4px] border transition-colors duration-200 ${isRunning ? 'border-ops-cyan/35 bg-ops-cyan/10 text-ops-cyan' : approvalStatus === 'pending' ? 'border-ops-warning/35 bg-ops-warning/10 text-ops-warning' : 'border-ops-border/35 bg-ops-deep/60 text-ops-muted'}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="text-[9px] font-bold tracking-[0.1em] text-ops-muted/50">{isCommandTool ? t('conversation.command') : t('conversation.toolCall')}</span>
            <code className={`truncate font-mono text-[12px] ${isRunning ? 'text-ops-cyan' : 'text-ops-text/82'}`}>
              {toolSummary || (isCommandTool ? t('conversation.unknownCommand') : t('conversation.unknownTool'))}
            </code>
            {targetLabel ? <span className="truncate text-[10px] font-semibold text-ops-muted/60">目标：{targetLabel}</span> : null}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {(message ? !message.partial : !!endEvent) ? (
            <div className={`flex items-center gap-1.5 rounded-[4px] border px-2 py-0.5 text-[9px] font-bold tracking-[0.08em] ${exitCode === null || exitCode === 0 ? 'border-ops-green/25 bg-ops-green/8 text-ops-green' : 'border-ops-danger/30 bg-ops-danger/8 text-ops-danger'}`}>
              <div className={`h-1.5 w-1.5 rounded-full ${exitCode === null || exitCode === 0 ? 'bg-ops-green' : 'bg-ops-danger'}`} />
              {exitCode === null || exitCode === 0 ? t('conversation.success') : t('conversation.errorCode', { code: String(exitCode) })}
            </div>
          ) : approvalStatus ? (
            <div className={`flex items-center gap-1.5 rounded-[4px] border px-2 py-0.5 text-[9px] font-bold tracking-[0.08em] ${approvalStatus === 'approved' ? 'border-ops-green/25 bg-ops-green/8 text-ops-green' : approvalStatus === 'rejected' ? 'border-ops-danger/30 bg-ops-danger/8 text-ops-danger' : 'border-ops-warning/35 bg-ops-warning/10 text-ops-warning'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${approvalStatus === 'approved' ? 'bg-ops-green' : approvalStatus === 'rejected' ? 'bg-ops-danger' : 'animate-pulse bg-ops-warning'}`} />
              {approvalStatus === 'approved' ? t('conversation.authorized') : approvalStatus === 'rejected' ? t('conversation.denied') : t('conversation.needsApproval')}
            </div>
          ) : (
            <div className="flex items-center gap-1.5 rounded-[4px] border border-ops-cyan/30 bg-ops-cyan/8 px-2 py-0.5 text-[9px] font-bold tracking-[0.08em] text-ops-cyan">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-cyan" />
              {t('conversation.running')}
            </div>
          )}

          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex h-6 w-6 items-center justify-center rounded-[4px] border border-ops-border/35 bg-ops-deep/60 text-ops-muted transition-all duration-200 hover:border-ops-cyan/35 hover:text-ops-cyan active:scale-95"
          >
            <svg 
              width="12" 
              height="12" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2.5" 
              className={`transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
            >
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="mt-3 flex flex-col gap-3 border-t border-ops-border/20 pt-3 animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="flex flex-col gap-1.5">
            <span className="text-[9px] font-black uppercase tracking-[0.16em] text-ops-muted/48">{isCommandTool ? t('conversation.commandPayload') : t('conversation.toolArgs')}</span>
            <code className="block whitespace-pre-wrap break-all rounded-[4px] border border-ops-border/30 bg-black/60 px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ops-text/90 shadow-inner">
              {isCommandTool ? displayCommand : argsJson}
            </code>
          </div>

          {showApprovalActions && approvalStatus === 'pending' && (
            <section className="relative overflow-hidden rounded-[5px] border border-ops-warning/40 bg-ops-warning/[0.06] p-3 shadow-inner">
              <div className="pointer-events-none absolute bottom-0 left-0 top-0 w-0.5 bg-ops-warning/80" />
              <div className="mb-3 flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[4px] border border-ops-warning/35 bg-ops-warning/10 text-ops-warning">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3 3.5 19h17L12 3Z" /><path d="M12 8v5" /><path d="M12 17h.01" /></svg>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold tracking-[0.1em] text-ops-warning">{t('conversation.riskCheckpoint')}</div>
                    <div className="mt-0.5 text-[12px] font-semibold text-ops-text">{t('conversation.needsOperatorApproval', { kind: isCommandTool ? t('conversation.commandKind') : t('conversation.toolCallKind') })}</div>
                  </div>
                </div>
                <span className="rounded-[4px] border border-ops-warning/30 bg-ops-deep/60 px-2 py-0.5 text-[9px] font-bold tracking-[0.08em] text-ops-warning/85">{t('conversation.needsApproval')}</span>
              </div>

              {(message?.text || approvalEvent?.reason) && <div className="mb-3 rounded-[4px] border border-ops-warning/20 bg-ops-deep/55 px-3 py-2 text-[12px] leading-relaxed text-ops-text/78">{message?.text || approvalEvent?.reason}</div>}

              {isCommandTool && showWhitelistOptions ? (
                <div className="mb-3 rounded-[4px] border border-ops-border/25 bg-ops-deep/55 p-2.5">
                  <div className="mb-2 text-[10px] font-black uppercase tracking-[0.14em] text-ops-muted/68">{t('conversation.whitelistPrefix')}</div>
                  <div className="mb-3 flex flex-wrap gap-2">
                    {allowPrefixOptions.map((option) => (
                      <button
                        key={option}
                        type="button"
                        className={`rounded-[4px] border px-2.5 py-1 font-mono text-[11px] transition-all duration-200 active:scale-95 ${allowPrefix === option ? 'border-ops-cyan/45 bg-ops-cyan/12 text-ops-cyan' : 'border-ops-border/30 bg-ops-panel/30 text-ops-muted hover:text-ops-text'}`}
                        onClick={() => setAllowPrefix(option)}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                  <input
                    className="field-control h-9 w-full font-mono text-[12px]"
                    value={allowPrefix}
                    onChange={(event) => setAllowPrefix(event.target.value)}
                    placeholder={t('conversation.whitelistPrefixPlaceholder')}
                  />
                </div>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3">
                {isCommandTool ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (!showWhitelistOptions) {
                        setAllowPrefix(allowPrefixOptions[0] ?? '')
                        setShowWhitelistOptions(true)
                        return
                      }
                      onApprove?.(allowPrefix)
                    }}
                    className="rounded-[4px] border border-ops-cyan/30 bg-ops-cyan/8 px-3 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-cyan transition-all duration-200 hover:border-ops-cyan/45 hover:bg-ops-cyan/14 active:scale-95 disabled:cursor-not-allowed disabled:opacity-45"
                    disabled={showWhitelistOptions && !allowPrefix.trim()}
                  >
                    {showWhitelistOptions ? t('conversation.approveTrustPrefix') : t('conversation.trustCommandPrefix')}
                  </button>
                ) : <span />}
                <div className="flex items-center gap-2">
                  <button type="button" onClick={onReject} className="rounded-[4px] border border-ops-danger/30 bg-ops-danger/8 px-3 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-danger transition-all duration-200 hover:border-ops-danger/45 hover:bg-ops-danger/12 active:scale-95">{t('conversation.reject')}</button>
                  <button type="button" onClick={() => onApprove?.()} className="rounded-[4px] border border-ops-warning/45 bg-ops-warning px-3 py-1.5 text-[10px] font-bold tracking-[0.08em] text-ops-deep transition-all duration-200 hover:bg-ops-warning/85 active:scale-95">{t('conversation.approveOnce')}</button>
                </div>
              </div>
            </section>
          )}

          {hasExecutionResult && (
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-bold tracking-[0.1em] text-ops-muted/60">{t('conversation.executionOutput')}</span>
              {structuredOutput ? <StructuredTerminalToolOutput output={structuredOutput} /> : <OutputBlock text={outputText || t('conversation.noOutput')} />}
            </div>
          )}
        </div>
      )}

      {!isExpanded && hasExecutionResult && (
        <div className="mt-1.5 ml-9 flex items-center gap-2 overflow-hidden border-t border-ops-border/10 pt-1.5">
          <span className="shrink-0 text-[9px] font-bold tracking-[0.05em] text-ops-muted/40">{t('conversation.output')}</span>
          <span className="truncate font-mono text-[11px] text-ops-muted/60">
            {outputText.split('\n').filter(l => l.trim()).pop() || outputText.slice(-100) || t('conversation.noOutput')}
          </span>
        </div>
      )}
    </div>
  )
}
