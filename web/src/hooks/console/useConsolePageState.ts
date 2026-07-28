import { useEffect, useMemo, useState } from 'react'
import type { RunMode } from '../../types/api'
import type { EventItem, RuntimeSnapshot } from '../../types/ops'

type UseConsolePageStateProps = {
  events: EventItem[]
  activeRuntimeSnapshot: RuntimeSnapshot | null
}

export function useConsolePageState({ events, activeRuntimeSnapshot }: UseConsolePageStateProps) {
  const [activeModal, setActiveModal] = useState<'settings' | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [runMode, setRunMode] = useState<RunMode>('agent')

  useEffect(() => {
    if (activeRuntimeSnapshot) {
      setRunMode(activeRuntimeSnapshot.mode)
      return
    }
    const latestPlanEvent = [...events].reverse().find((event) => event.kind === 'plan')
    if (latestPlanEvent?.mode) {
      setRunMode(latestPlanEvent.mode)
    }
  }, [activeRuntimeSnapshot, events])

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
    runMode,
    setRunMode,
    busyCommand,
  }
}
