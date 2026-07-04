import { type ReactNode, type ComponentProps } from 'react'
import { motion, type Variants, type Transition } from 'framer-motion'

// ── Token-scale durations ──
const DURATIONS = {
  fast: 0.14,
  normal: 0.22,
  slow: 0.34,
} as const

// ── Token-scale easing ──
const EASING = {
  out: [0.0, 0.0, 0.2, 1.0] as [number, number, number, number],
  in: [0.4, 0.0, 1.0, 1.0] as [number, number, number, number],
  spring: { type: 'spring' as const, stiffness: 400, damping: 28, mass: 0.8 },
}

// ── Shared transitions ──
/** Standard ease-out transition (opacity/transform only) */
export const easeOut: Transition = {
  duration: DURATIONS.normal,
  ease: EASING.out,
}

/** Slightly faster ease-out for micro-interactions */
export const easeOutFast: Transition = {
  duration: DURATIONS.fast,
  ease: EASING.out,
}

/** Spring-based transition for layout changes – snappy, minimal bounce */
export const layoutSpring: Transition = {
  ...EASING.spring,
}

// ── Card / block entrance (fade + translate y) ──
/** Standard card entrance: fade in + slide up 8px */
export const cardEntrance: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: easeOut },
}

/** Card entrance with reduced motion — opacity only */
export const cardEntranceReduced: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: easeOut },
}

// ── Scale entrance (for modals, dialogs, significant blocks) ──
export const scaleEntrance: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1, transition: easeOut },
}

// ── Staggered children (for grouped cards / message lists) ──
export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.04,
      delayChildren: 0.02,
    },
  },
}

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: easeOut },
}

// ── Expand / collapse ──
export const expandCollapse: Variants = {
  collapsed: { height: 0, opacity: 0, overflow: 'hidden' },
  expanded: { height: 'auto', opacity: 1, overflow: 'hidden', transition: easeOut },
}

// ── Status indicator pulse (low-frequency, non-distracting) ──
export const statusPulse: Variants = {
  idle: { scale: 1, opacity: 0.6 },
  active: {
    scale: [1, 1.15, 1],
    opacity: [0.6, 1, 0.6],
    transition: { duration: 2.4, repeat: Infinity, ease: 'easeInOut' },
  },
}

// ── Batch transition prop helpers (spread-ready objects) ──

/** Spread into <motion.div> for a standard card/block entrance */
export const cardMotionProps = {
  variants: cardEntrance,
  initial: 'hidden',
  animate: 'visible',
} as const

/** Spread into a staggered container – wraps multiple items */
export const staggerContainerProps = {
  variants: staggerContainer,
  initial: 'hidden',
  animate: 'visible',
} as const

/** Spread into each item inside a stagger container */
export const staggerItemProps = {
  variants: staggerItem,
} as const

// ══════════════════════════════════════════════════════════
//  React Components
// ══════════════════════════════════════════════════════════

// ── OpsFadeIn ──
// 通用容器入场：fade + translate y。适合任何卡片/区块的首次渲染入场。
type OpsFadeInProps = ComponentProps<typeof motion.div> & {
  as?: 'div' | 'section' | 'article' | 'span' | 'main'
}
export function OpsFadeIn({ as: tag = 'div', children, className, ...rest }: OpsFadeInProps) {
  const MotionTag = motion[tag as keyof typeof motion] as typeof motion.div
  return (
    <MotionTag className={className} variants={cardEntrance} initial="hidden" animate="visible" {...rest}>
      {children}
    </MotionTag>
  )
}

// ── OpsScaleIn ──
// 缩放入场。适合弹窗、Dialog、重要区块。
type OpsScaleInProps = ComponentProps<typeof motion.div> & {
  as?: 'div' | 'section' | 'article'
}
export function OpsScaleIn({ as: tag = 'div', children, className, ...rest }: OpsScaleInProps) {
  const MotionTag = motion[tag as keyof typeof motion] as typeof motion.div
  return (
    <MotionTag className={className} variants={scaleEntrance} initial="hidden" animate="visible" {...rest}>
      {children}
    </MotionTag>
  )
}

// ── OpsAnimatedGroup ──
// 错落入场容器。包裹一组子元素，每个子元素将依次错落显现。
type OpsAnimatedGroupProps = ComponentProps<typeof motion.div> & {
  as?: 'div' | 'section' | 'ul' | 'ol'
  staggerDelay?: number
  delayChildren?: number
}
export function OpsAnimatedGroup({
  children,
  className,
  as: tag = 'div',
  staggerDelay = 0.04,
  delayChildren = 0.02,
  ...rest
}: OpsAnimatedGroupProps) {
  const containerVariants: Variants = {
    hidden: {},
    visible: {
      transition: { staggerChildren: staggerDelay, delayChildren },
    },
  }
  const MotionTag = motion[tag as keyof typeof motion] as typeof motion.div
  return (
    <MotionTag
      className={className}
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      {...rest}
    >
      {children}
    </MotionTag>
  )
}

// ── OpsAnimatedItem ──
// 配合 OpsAnimatedGroup 使用的子项包装。
type OpsAnimatedItemProps = ComponentProps<typeof motion.div> & {
  as?: 'div' | 'li'
}
export function OpsAnimatedItem({ children, className, as: tag = 'div', ...rest }: OpsAnimatedItemProps) {
  const MotionTag = motion[tag as keyof typeof motion] as typeof motion.div
  return (
    <MotionTag className={className} variants={staggerItem} {...rest}>
      {children}
    </MotionTag>
  )
}

// ── OpsExpandCollapse ──
// 展开/折叠容器。通过 isExpanded 控制内容区域的显隐（带动画）。
type OpsExpandCollapseProps = {
  isExpanded: boolean
  children: ReactNode
  className?: string
}
export function OpsExpandCollapse({ isExpanded, children, className }: OpsExpandCollapseProps) {
  return (
    <motion.div
      className={className}
      variants={expandCollapse}
      initial="collapsed"
      animate={isExpanded ? 'expanded' : 'collapsed'}
    >
      {children}
    </motion.div>
  )
}

// ── OpsStatusPulse ──
// 状态指示器脉冲。替代现有 animate-pulse 的 Tailwind 类。
type OpsStatusPulseProps = {
  active: boolean
  color?: 'green' | 'warning' | 'danger' | 'muted'
  className?: string
  size?: number
}
const pulseColors: Record<string, string> = {
  green: 'bg-ops-green',
  warning: 'bg-ops-warning',
  danger: 'bg-ops-danger',
  muted: 'bg-ops-muted',
}
export function OpsStatusPulse({ active, color = 'green', className = '', size = 6 }: OpsStatusPulseProps) {
  return (
    <motion.span
      className={`inline-block rounded-full ${pulseColors[color] ?? pulseColors.green} ${className}`}
      variants={statusPulse}
      initial="idle"
      animate={active ? 'active' : 'idle'}
      style={{ width: size, height: size }}
    />
  )
}

// ── OpsBackdrop ──
// 模态遮罩层。淡入。
type OpsBackdropProps = {
  onClick?: () => void
  className?: string
}
export function OpsBackdrop({ onClick, className = '' }: OpsBackdropProps) {
  return (
    <motion.div
      className={`fixed inset-0 z-40 bg-ops-bg/60 backdrop-blur-md ${className}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: easeOutFast }}
      exit={{ opacity: 0, transition: easeOutFast }}
      onClick={onClick}
      role="presentation"
    />
  )
}