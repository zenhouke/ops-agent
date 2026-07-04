import type { SelectHTMLAttributes } from 'react'

type SelectOption = {
  label: string
  value: string
}

type SelectFieldProps = {
  label: string
  options: SelectOption[]
} & SelectHTMLAttributes<HTMLSelectElement>

export function SelectField({ label, id, options, className = '', ...props }: SelectFieldProps) {
  const mergedClassName = `bg-ops-panel text-ops-text text-sm rounded border border-ops-border/20 px-2 py-1 outline-none focus:border-ops-green transition-colors ${className}`.trim()

  return (
    <>
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <select id={id} className={mergedClassName} {...props}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </>
  )
}
