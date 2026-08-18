import type { AgentMessage } from '../../../types/ops'
import { useMemo, useState } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PROSE_CLASS } from './types'
import { stripInvisibleMarkers, stripJsonBlocks } from './utils'
import { CommandExecutionCard } from './CommandExecutionCard'

type AssistantMessageContentProps = {
  content?: string
  message?: AgentMessage
  isStreaming?: boolean
  onApprove?: (allowPrefix?: string) => void
  onReject?: () => void
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

  // Extract thinking from message.thinking field or parse <think>...</think> tags
  const parsed = useMemo(() => {
    // Priority 1: Use message.thinking if available (from reasoning models)
    if (message?.thinking) {
      const thinking = stripInvisibleMarkers(message.thinking)
      const isStillThinking = message.partial && thinking.length > 0 && !processedContent
      return {
        thinking,
        output: processedContent,
        isThinkingOnly: false,
        isStillThinking
      }
    }

    // Priority 2: Parse <think>...</think> tags (legacy support)
    const thinkStart = processedContent.indexOf('<think>')
    const thinkEnd = processedContent.indexOf('</think>')

    if (thinkStart !== -1) {
      if (thinkEnd !== -1) {
        // Full block found
        const thinking = processedContent.slice(thinkStart + 7, thinkEnd).trim()
        const output = processedContent.slice(thinkEnd + 8).trim()
        return { thinking, output, isThinkingOnly: false, isStillThinking: false }
      } else {
        // Open block found
        const thinking = processedContent.slice(thinkStart + 7).trim()
        return { thinking, output: '', isThinkingOnly: true, isStillThinking: true }
      }
    }

    return { thinking: '', output: processedContent, isThinkingOnly: false, isStillThinking: false }
  }, [processedContent, message])

  const [isThinkExpanded, setIsThinkExpanded] = useState(false)

  if (!parsed.thinking && !parsed.output && !message?.toolCall) {
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
        执行记录
        {isStreaming && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-cyan" />}
      </div>

      <div className="flex flex-col gap-3">
        {parsed.thinking && (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              aria-expanded={isThinkExpanded}
              onClick={() => setIsThinkExpanded(!isThinkExpanded)}
              className="flex w-fit items-center gap-2 rounded-[4px] border border-ops-cyan/10 bg-ops-cyan/5 px-2.5 py-1 text-[10px] font-semibold text-ops-cyan/65 transition-colors hover:border-ops-cyan/25 hover:text-ops-cyan active:scale-95"
            >
              <div className={`flex h-4 w-4 items-center justify-center rounded-full border border-ops-cyan/25 bg-ops-deep/50 transition-transform duration-200 ${isThinkExpanded ? 'rotate-180' : ''}`}>
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="m6 9 6 6 6-6"/></svg>
              </div>
              <span>{parsed.isStillThinking ? t('conversation.thinkingInProgress') : t('conversation.thoughtProcess')}</span>
              {parsed.isStillThinking && isStreaming && <span className="h-1 w-1 animate-pulse rounded-full bg-ops-cyan" />}
            </button>

            {isThinkExpanded && (
              <div className="relative overflow-hidden rounded-[4px] border border-ops-border/20 bg-ops-deep/45 px-4 py-3 text-[13px] leading-relaxed text-ops-muted/80 shadow-inner animate-in fade-in slide-in-from-top-1 duration-200">
                <div className="absolute left-0 top-0 h-full w-0.5 bg-ops-cyan/30" />
                <div className="prose prose-invert prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:my-2 [&_code]:rounded [&_code]:bg-ops-deep [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[11px] [&_pre]:my-3 [&_pre]:rounded-lg [&_pre]:bg-ops-deep [&_pre]:p-3 [&_pre>code]:text-[11px]">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{parsed.thinking}</ReactMarkdown>
                </div>
                {parsed.isStillThinking && isStreaming && (
                  <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-ops-cyan/85 align-[-2px]" />
                )}
              </div>
            )}
          </div>
        )}

        {parsed.output && (
          <div className={PROSE_CLASS}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{parsed.output}</ReactMarkdown>
            {(isStreaming || (message?.partial && !message?.toolCall)) && !parsed.isStillThinking && (
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
