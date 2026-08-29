import type { Layout } from 'react-resizable-panels'

const DEFAULT_TASK_TERMINAL_LAYOUT: Layout = { task: 58, terminal: 42 }

export function getStoredTerminalOpen() {
  return localStorage.getItem('ops-agent:terminal-open') === 'true'
    || localStorage.getItem('ops-agent:workspace-view') === 'terminal'
}

export function getStoredTaskTerminalLayout(): Layout {
  try {
    const value = JSON.parse(localStorage.getItem('ops-agent:task-terminal-layout') ?? '') as Layout
    if (typeof value.task === 'number' && typeof value.terminal === 'number') return value
  } catch {
    // Ignore stale or invalid local layout state.
  }
  return DEFAULT_TASK_TERMINAL_LAYOUT
}
