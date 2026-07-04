import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ListItemCardProps = {
  title: string
  meta: string
  active?: boolean
  children?: ReactNode
} & ButtonHTMLAttributes<HTMLButtonElement>

export function ListItemCard({ title, meta, active = false, className = '', children, type = 'button', ...props }: ListItemCardProps) {
  const baseClassName = `w-full flex flex-col items-start border-l-2 px-5 py-3.5 text-left transition-all duration-200 active:scale-[0.98] ${active ? 'border-l-ops-green bg-ops-green/10 text-ops-text shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]' : 'border-l-transparent bg-transparent text-ops-muted hover:bg-ops-panel/60 hover:text-ops-text'}`
  const mergedClassName = className ? `${baseClassName} ${className}` : baseClassName

  return (
    <button type={type} className={mergedClassName} {...props}>
      <span className={`w-full truncate text-[13px] font-bold tracking-tight ${active ? 'text-ops-green' : ''}`}>{title}</span>
      <span className="mt-1 w-full truncate text-[10px]  tracking-[0.15em] font-medium opacity-60">{meta}</span>
      {children}
    </button>
  )
}
