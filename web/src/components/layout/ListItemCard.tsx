import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ListItemCardProps = {
  title: string
  meta: string
  active?: boolean
  children?: ReactNode
} & ButtonHTMLAttributes<HTMLButtonElement>

export function ListItemCard({ title, meta, active = false, className = '', children, type = 'button', ...props }: ListItemCardProps) {
  const baseClassName = `w-full flex flex-col items-start border-l-2 px-3 py-2.5 text-left transition-all duration-200 active:scale-[0.98] ${active ? 'border-l-ops-cyan bg-ops-cyan/10 text-ops-text' : 'border-l-transparent bg-transparent text-ops-muted hover:bg-ops-panel/60 hover:text-ops-text'}`
  const mergedClassName = className ? `${baseClassName} ${className}` : baseClassName

  return (
    <button type={type} className={mergedClassName} {...props}>
      <span className={`w-full truncate text-[12px] font-semibold tracking-tight ${active ? 'text-ops-cyan' : ''}`}>{title}</span>
      <span className="mt-0.5 w-full truncate font-mono text-[9px] font-medium tracking-[0.06em] opacity-60">{meta}</span>
      {children}
    </button>
  )
}
