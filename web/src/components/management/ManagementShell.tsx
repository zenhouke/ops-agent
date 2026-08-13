import type { ReactNode } from 'react'

type ManagementShellProps = {
  title: string
  description: string
  eyebrow?: string
  actions?: ReactNode
  children: ReactNode
}

export function ManagementShell({ title, description, eyebrow = '管理', actions, children }: ManagementShellProps) {
  return (
    <section className="flex h-full min-h-0 flex-col bg-ops-bg" aria-labelledby="management-workspace-title">
      <header className="flex min-h-16 shrink-0 items-center justify-between gap-6 border-b border-ops-border/30 bg-ops-deep/45 px-6 py-3">
        <div className="min-w-0">
          <div className="text-[9px] font-semibold tracking-[0.12em] text-ops-muted/55">{eyebrow}</div>
          <h1 id="management-workspace-title" className="mt-0.5 truncate text-[15px] font-semibold text-ops-text">{title}</h1>
          <p className="mt-0.5 truncate text-[10px] text-ops-muted/65">{description}</p>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1120px] p-6">{children}</div>
      </div>
    </section>
  )
}
