import type { AgentMessage } from '../../../types/ops'
import { useMemo } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PROSE_CLASS } from './types'
import { stripJsonBlocks } from './utils'
import { CommandExecutionCard } from './CommandExecutionCard'

type AssistantMessageContentProps = {
  content?: string
  message?: AgentMessage
  isStreaming?: boolean
  onApprove?: (allowPrefix?: string, guidance?: string) => void
  onReject?: (guidance?: string) => void
  pendingApprovalRuntimeId?: string | null
}

export function AssistantMessageContent({ 
  content, 
  message, 
  isStreaming, 
  onApprove, 
  onReject, 
  pendingApprovalRuntimeId 
}: AssistantMessageContentProps) {
  const { t } = useAppearance()
  const finalContent = useMemo(() => {
    if (message) return message.text || ''
    return content || ''
  }, [content, message])

  const processedContent = useMemo(() => stripJsonBlocks(finalContent), [finalContent])

  const parsed = useMemo(() => {
    const thinkStart = processedContent.indexOf('<think>')
    const thinkEnd = processedContent.indexOf('</think>')
    if (thinkStart !== -1) {
      if (thinkEnd !== -1) {
        const output = processedContent.slice(thinkEnd + 8).trim()
        return { output }
      }
      return { output: '' }
    }
    return { output: processedContent }
  }, [processedContent])

  if (!parsed.output && !message?.toolCall) {
    // Show a loading indicator when the message is partial (LLM hasn't produced tokens yet)
    if (message?.partial || isStreaming) {
      return (
        <div className="flex w-fit items-center gap-3 rounded-full border border-ops-cyan/10 bg-ops-panel/45 px-4 py-2 text-ops-muted/70 shadow-[0_12px_32px_rgba(0,0,0,0.18)]">
          <div className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-cyan/70" style={{ animationDelay: '0ms' }} />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-cyan/70" style={{ animationDelay: '200ms' }} />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-cyan/70" style={{ animationDelay: '400ms' }} />
          </div>
          <span className="text-[10px] font-black uppercase tracking-[0.16em] text-ops-muted/55">{t('conversation.thinking')}</span>
        </div>
      )
    }
    return null
  }

  return (
    <article className="relative w-full py-1">
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold text-ops-muted/65">
        <span className="flex h-5 w-5 items-center justify-center rounded-[4px] border border-ops-cyan/20 bg-ops-cyan/8 text-[11px] text-ops-cyan">✦</span>
        {message?.ask === 'followup' ? 'Agent 需要确认' : 'Agent'}
        {isStreaming && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-cyan" />}
      </div>

      <div className="flex flex-col gap-3">
        {parsed.output && (
          <div className={PROSE_CLASS}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{parsed.output}</ReactMarkdown>
            {(isStreaming || (message?.partial && !message?.toolCall)) && (
              <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-ops-cyan/85 align-[-2px]" />
            )}
          </div>
        )}

        {message?.toolCall && (
          <CommandExecutionCard
            message={message}
            pendingApprovalRuntimeId={pendingApprovalRuntimeId ?? null}
            onApprove={onApprove}
            onReject={onReject}
          />
        )}
      </div>
    </article>
  )
}
