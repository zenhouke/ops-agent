import type { AgentMessage } from '../../../types/ops'
import { useMemo, useState } from 'react'
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
      const thinking = message.thinking
      const isStillThinking = message.partial && thinking.length > 0
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
        <div className="flex w-fit items-center gap-2.5 rounded-xl border border-ops-border/15 bg-ops-panel/40 px-4 py-2.5 text-ops-muted/60">
          <div className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-green/70" style={{ animationDelay: '0ms' }} />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-green/70" style={{ animationDelay: '200ms' }} />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-green/70" style={{ animationDelay: '400ms' }} />
          </div>
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-ops-muted/50">{t('conversation.thinking')}</span>
        </div>
      )
    }
    return null
  }

  return (
    <article className="relative w-full overflow-hidden rounded-2xl rounded-tl-sm border border-ops-border/20 bg-ops-panel/50 p-4 shadow-sm">
      <div className="mb-2.5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-ops-muted/50">
        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-ops-green/12 text-ops-green">
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a3 3 0 0 0-3 3v1a3 3 0 0 0-3 3v1a3 3 0 0 0-3 3v3a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-3a3 3 0 0 0-3-3V9a3 3 0 0 0-3-3V5a3 3 0 0 0-3-3z" /></svg>
        </span>
        {t('conversation.agentResponse')}
        {isStreaming && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ops-green" />}
      </div>

      <div className="flex flex-col gap-3">
        {parsed.thinking && (
          <div className="flex flex-col gap-2">
            <button
              onClick={() => setIsThinkExpanded(!isThinkExpanded)}
              className="flex w-fit items-center gap-1.5 rounded-lg px-2 py-1 text-[10px] font-bold uppercase tracking-[0.1em] text-ops-muted/60 transition-colors hover:bg-ops-panel/60 hover:text-ops-green"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className={`transition-transform duration-200 ${isThinkExpanded ? 'rotate-180' : ''}`}><path d="m6 9 6 6 6-6"/></svg>
              <span>{parsed.isStillThinking ? t('conversation.thinkingInProgress') : t('conversation.thoughtProcess')}</span>
              {parsed.isStillThinking && isStreaming && <span className="h-1 w-1 animate-pulse rounded-full bg-ops-green" />}
            </button>

            {isThinkExpanded && (
              <div className="overflow-hidden rounded-xl border border-ops-border/15 bg-ops-deep/40 px-4 py-3 text-[13px] leading-relaxed text-ops-muted/75 animate-in fade-in slide-in-from-top-1 duration-200">
                <div className="prose prose-invert prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:my-2 [&_code]:rounded [&_code]:bg-ops-deep [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[11px] [&_pre]:my-3 [&_pre]:rounded-lg [&_pre]:bg-ops-deep [&_pre]:p-3 [&_pre>code]:text-[11px]">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{parsed.thinking}</ReactMarkdown>
                </div>
                {parsed.isStillThinking && isStreaming && (
                  <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-ops-green/85 align-[-2px]" />
                )}
              </div>
            )}
          </div>
        )}

        {parsed.output && (
          <div className={PROSE_CLASS}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{parsed.output}</ReactMarkdown>
            {(isStreaming || (message?.partial && !message?.toolCall)) && !parsed.isStillThinking && (
              <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-ops-green/85 align-[-2px]" />
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
