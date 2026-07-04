import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'default' | 'primary' | 'danger' | 'tab-active'

type ButtonProps = {
  children: ReactNode
  variant?: ButtonVariant
} & ButtonHTMLAttributes<HTMLButtonElement>

export function Button({ children, className = '', variant = 'default', type = 'button', ...props }: ButtonProps) {
  const baseClasses = 'inline-flex items-center justify-center rounded-md border px-4 py-2 text-sm font-medium transition-all duration-200 active:scale-95 focus:outline-none'
  const variantClassName = {
    default: 'border-ops-border/40 bg-ops-panel text-ops-text hover:border-ops-border hover:bg-ops-deep',
    primary: 'border-ops-green/50 bg-ops-green/10 text-ops-green hover:border-ops-green hover:bg-ops-green/20 hover:shadow-glow',
    danger: 'border-ops-danger/50 bg-ops-danger/10 text-ops-danger hover:border-ops-danger hover:bg-ops-danger/20',
    'tab-active': 'rounded-none border-b-2 border-b-ops-green border-x-ops-border/40 border-t-transparent bg-ops-deep text-ops-green',
  }[variant]

  const mergedClassName = `${baseClasses} ${variantClassName} ${className}`.trim()

  return (
    <button type={type} className={mergedClassName} {...props}>
      {children}
    </button>
  )
}

export function PrimaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button variant="primary" {...props} />
}

export function DangerButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button variant="danger" {...props} />
}

export function SecondaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button variant="default" {...props} />
}
