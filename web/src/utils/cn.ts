import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * 合并 Tailwind CSS 类名，自动解决冲突。
 *
 * 用法：cn('px-2 py-1', condition && 'bg-red-500', 'px-4')
 * → 'py-1 bg-red-500 px-4'  （px-4 覆盖 px-2）
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
