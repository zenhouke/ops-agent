import { useMemo, useState } from 'react'
import type { EventItem } from '../../types/ops'

type UseConsolePageStateProps = {
  events: EventItem[]
}

export function useConsolePageState({ events }: UseConsolePageStateProps) {
  const [activeModal, setActiveModal] = useState<'settings' | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const busyCommand = useMemo(() => {
    const commandsInOrder: Array<{ id: string; cmd: string }> = []
    const ended = new Set<string>()
    for (const evt of events) {
      if (evt.kind === 'command_start') {
        commandsInOrder.push({ id: evt.commandId, cmd: evt.command })
      } else if (evt.kind === 'command_end') {
        ended.add(evt.commandId)
      }
    }
    for (let i = commandsInOrder.length - 1; i >= 0; i -= 1) {
      const item = commandsInOrder[i]
      if (!ended.has(item.id)) return item.cmd
    }
    return null
  }, [events])

  return {
    activeModal,
    setActiveModal,
    sidebarCollapsed,
    setSidebarCollapsed,
    busyCommand,
  }
}
