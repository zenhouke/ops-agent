import type { EventItem, CommandStartEvent, CommandChunkEvent, CommandEndEvent, ApprovalEvent, ExecutionStartedEvent, ExecutionOutputEvent, ExecutionCompletedEvent, AgentMessage } from '../../../types/ops'

export type DeltaEvent = Extract<EventItem, { kind: 'delta' }>
export type CommandStart = CommandStartEvent | ExecutionStartedEvent
export type CommandChunk = CommandChunkEvent | ExecutionOutputEvent
export type CommandEnd = CommandEndEvent | ExecutionCompletedEvent
export type Approval = ApprovalEvent

export type Group =
  | { type: 'event'; event: EventItem }
  | { type: 'thinking'; deltas?: DeltaEvent[]; message?: AgentMessage; key: string }
  | {
    type: 'command'
    key: string
    message?: AgentMessage
    approvalEvent?: Approval
    startEvent?: CommandStart
    chunkEvents: CommandChunk[]
    endEvent?: CommandEnd
  }

export const STAGE_ORDER = ['assistant'] as const
export const STAGE_LABEL: Record<string, string> = {
  assistant: 'AI Output',
}
export const STAGE_ICON_COLOR: Record<string, string> = {
  assistant: 'text-ops-cyan',
}

export const PROSE_CLASS =
  'prose prose-invert prose-sm max-w-none text-[14px] leading-7 text-ops-text/90 ' +
  '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0 ' +
  '[&_h1]:mb-4 [&_h1]:mt-6 [&_h1]:text-[19px] [&_h1]:font-black [&_h1]:tracking-[0.01em] [&_h1]:text-ops-text ' +
  '[&_h2]:mb-3 [&_h2]:mt-5 [&_h2]:text-[16px] [&_h2]:font-bold [&_h2]:text-ops-cyan/95 ' +
  '[&_h3]:mb-2 [&_h3]:mt-4 [&_h3]:text-[14px] [&_h3]:font-bold [&_h3]:uppercase [&_h3]:tracking-[0.12em] [&_h3]:text-ops-muted ' +
  '[&_h4]:mb-1.5 [&_h4]:mt-3 [&_h4]:text-[14px] [&_h4]:font-semibold [&_h4]:text-ops-text/90 ' +
  '[&_p]:my-3 [&_p]:text-indent-[2em] [&_p:first-of-type]:text-indent-0 [&_li_p]:text-indent-0 [&_blockquote_p]:text-indent-0 ' +
  '[&_ul]:my-3 [&_ul]:space-y-1.5 [&_ul]:pl-5 ' +
  '[&_ol]:my-3 [&_ol]:space-y-1.5 [&_ol]:pl-5 ' +
  '[&_li]:pl-1 [&_li]:leading-7 [&_li]:text-ops-text/88 ' +
  '[&_li::marker]:text-ops-cyan/75 ' +
  '[&_code]:rounded-md [&_code]:border [&_code]:border-ops-cyan/10 [&_code]:bg-ops-deep/90 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[12px] [&_code]:text-ops-cyan ' +
  '[&_pre]:my-4 [&_pre]:overflow-x-auto [&_pre]:rounded-2xl [&_pre]:border [&_pre]:border-ops-border/30 [&_pre]:bg-ops-deep/95 [&_pre]:p-4 [&_pre]:shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] ' +
  '[&_pre>code]:border-0 [&_pre>code]:bg-transparent [&_pre>code]:p-0 [&_pre>code]:text-ops-text/85 ' +
  '[&_blockquote]:my-4 [&_blockquote]:rounded-r-2xl [&_blockquote]:border-l-2 [&_blockquote]:border-ops-cyan/55 [&_blockquote]:bg-ops-cyan/6 [&_blockquote]:py-2.5 [&_blockquote]:pl-4 [&_blockquote]:text-ops-text/72 ' +
  '[&_table]:my-4 [&_table]:w-full [&_table]:overflow-hidden [&_table]:rounded-2xl [&_table]:border [&_table]:border-ops-border/25 ' +
  '[&_thead]:bg-ops-cyan/8 ' +
  '[&_th]:border-b [&_th]:border-ops-cyan/20 [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:text-[11px] [&_th]:font-black [&_th]:uppercase [&_th]:tracking-[0.12em] [&_th]:text-ops-cyan ' +
  '[&_td]:border-b [&_td]:border-ops-border/15 [&_td]:px-3 [&_td]:py-2.5 [&_td]:text-[13px] [&_td]:text-ops-text/86 ' +
  '[&_tbody_tr:last-child_td]:border-b-0 ' +
  '[&_strong]:font-bold [&_strong]:text-ops-text [&_em]:text-ops-text/78 ' +
  '[&_a]:text-ops-cyan [&_a]:underline-offset-4 hover:[&_a]:text-ops-text'
