import { useState } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import { stripAnsi } from './utils'

type OutputBlockProps = {
  text: string
  label?: string
}

export function OutputBlock({ text, label }: OutputBlockProps) {
  const { t } = useAppearance()
  const [isExpanded, setIsExpanded] = useState(false)
  const cleanText = stripAnsi(text)
  const lines = cleanText.split('\n')
  const shouldTruncate = lines.length > 10

  return (
    <div className="flex w-full flex-col gap-0 overflow-hidden rounded-lg border border-ops-border/15">
      <div className="flex items-center justify-between bg-ops-deep/60 px-3 py-1.5 border-b border-ops-border/10">
        <span className="text-[10px] font-bold tracking-[0.12em] uppercase text-ops-muted/60">{label ?? t('conversation.terminalOutput')}</span>
        {shouldTruncate ? (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-[10px] font-bold tracking-wide text-ops-green/80 hover:text-ops-green transition-colors"
          >
            {isExpanded ? t('conversation.collapse') : t('conversation.expandLines', { count: String(lines.length) })}
          </button>
        ) : null}
      </div>
      <pre
        className={`m-0 whitespace-pre-wrap bg-ops-deep/30 p-3.5 font-mono text-[11px] leading-[1.6] text-ops-text/75 transition-all ${!isExpanded && shouldTruncate ? 'relative max-h-[200px] overflow-hidden' : 'max-h-none'
          }`}
      >
        {cleanText}
        {!isExpanded && shouldTruncate ? <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-ops-deep/90 to-transparent" /> : null}
      </pre>
    </div>
  )
}
