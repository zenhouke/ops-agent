import { useState } from 'react'
import { useAppearance } from '../../../hooks/useAppearance'
import { stripAnsi } from '../../../utils/terminalText'

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
    <div className="flex w-full flex-col gap-0 overflow-hidden rounded-xl border border-ops-border/20 shadow-sm">
      <div className="flex items-center justify-between bg-ops-deep/80 px-4 py-2 border-b border-ops-border/10">
        <span className="text-[10px] font-bold tracking-[0.2em] text-ops-muted/70">{label ?? t('conversation.terminalOutput')}</span>
        {shouldTruncate ? (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-[10px] font-bold tracking-widest text-ops-cyan hover:text-ops-cyan/80 transition-colors"
          >
            {isExpanded ? t('conversation.collapse') : t('conversation.expandLines', { count: String(lines.length) })}
          </button>
        ) : null}
      </div>
      <pre
        className={`m-0 whitespace-pre-wrap bg-ops-deep/40 p-4 font-mono text-[11px] leading-normal text-ops-text/80 transition-all ${!isExpanded && shouldTruncate ? 'relative max-h-[200px] overflow-hidden' : 'max-h-none'
          }`}
      >
        {cleanText}
        {!isExpanded && shouldTruncate ? <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-ops-deep to-transparent" /> : null}
      </pre>
    </div>
  )
}
