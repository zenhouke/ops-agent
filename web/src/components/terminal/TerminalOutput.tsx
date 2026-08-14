import { useEffect, useRef } from 'react'
import { useAppearance } from '../../hooks/useAppearance'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { createTerminalTheme } from './terminalTheme'

type TerminalOutputProps = {
  sessionKey: string
  output: string
  onInput: (data: string) => void
  onResize: (cols: number, rows: number) => void
}

function stripReplayControlSequences(value: string) {
  return value
    .replace(/\u001b\[c/g, '')
    .replace(/\u001b\[\?1004h/g, '')
    .replace(/\u001b\[\?1004l/g, '')
    .replace(/\u001b\[\?9001h/g, '')
    .replace(/\u001b\[\?9001l/g, '')
}

export function TerminalOutput({ sessionKey, output, onInput, onResize }: TerminalOutputProps) {
  const { t, terminalBackground } = useAppearance()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const terminalHostRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const writtenLengthRef = useRef(0)
  const currentSessionKeyRef = useRef(sessionKey)
  const replayingRef = useRef(false)
  const onInputRef = useRef(onInput)
  const onResizeRef = useRef(onResize)
  const outputRef = useRef(output)
  const sessionKeyRef = useRef(sessionKey)
  const terminalBackgroundRef = useRef(terminalBackground)
  const lastSentInputRef = useRef<{ value: string; timestamp: number } | null>(null)

  useEffect(() => {
    onInputRef.current = onInput
    onResizeRef.current = onResize
    outputRef.current = output
    sessionKeyRef.current = sessionKey
    terminalBackgroundRef.current = terminalBackground
  }, [onInput, onResize, output, sessionKey, terminalBackground])

  const emitInput = (data: string) => {
    if (replayingRef.current || /^\u001b\[(I|O|\?1;2c)$/.test(data)) {
      return
    }

    onInputRef.current(data)
  }

  // Initialize terminal
  useEffect(() => {
    if (terminalHostRef.current === null) {
      return
    }

    const terminal = new Terminal({
      cursorBlink: true,
      fontFamily: 'JetBrains Mono, Cascadia Code, Consolas, monospace',
      fontSize: 13,
      theme: createTerminalTheme(terminalBackgroundRef.current),
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(terminalHostRef.current)

    let disposed = false

    void document.fonts.load('13px "JetBrains Mono"').then(() => {
      if (disposed) {
        return
      }
      terminal.options.fontFamily = 'JetBrains Mono, Cascadia Code, Consolas, monospace'
      requestAnimationFrame(() => {
        fitAddon.fit()
        onResizeRef.current(terminal.cols, terminal.rows)

        if (outputRef.current.length > 0) {
          replayingRef.current = true
          terminal.write(stripReplayControlSequences(outputRef.current))
          writtenLengthRef.current = outputRef.current.length
          queueMicrotask(() => {
            replayingRef.current = false
          })
        }
      })
    })

    terminal.onData((data) => emitInput(data))

    let resizeFrameId: number | null = null
    let resizeNotifyTimeoutId: number | null = null
    let lastNotifiedSize = { cols: terminal.cols, rows: terminal.rows }

    const notifyResize = () => {
      if (terminal.cols === lastNotifiedSize.cols && terminal.rows === lastNotifiedSize.rows) {
        return
      }
      lastNotifiedSize = { cols: terminal.cols, rows: terminal.rows }
      onResizeRef.current(terminal.cols, terminal.rows)
    }

    const scheduleResizeNotify = () => {
      if (resizeNotifyTimeoutId !== null) {
        window.clearTimeout(resizeNotifyTimeoutId)
      }
      resizeNotifyTimeoutId = window.setTimeout(() => {
        resizeNotifyTimeoutId = null
        notifyResize()
      }, 300)
    }

    const fitTerminal = () => {
      resizeFrameId = null
      fitAddon.fit()
      scheduleResizeNotify()
    }

    const scheduleFitTerminal = () => {
      if (resizeFrameId !== null) {
        window.cancelAnimationFrame(resizeFrameId)
      }
      resizeFrameId = window.requestAnimationFrame(fitTerminal)
    }

    const handleResize = () => {
      scheduleFitTerminal()
    }

    const resizeObserver = new ResizeObserver(() => {
      scheduleFitTerminal()
    })

    if (containerRef.current !== null) {
      resizeObserver.observe(containerRef.current)
    }

    window.addEventListener('resize', handleResize)
    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    return () => {
      disposed = true
      resizeObserver.disconnect()
      if (resizeFrameId !== null) {
        window.cancelAnimationFrame(resizeFrameId)
      }
      if (resizeNotifyTimeoutId !== null) {
        window.clearTimeout(resizeNotifyTimeoutId)
      }
      window.removeEventListener('resize', handleResize)
      terminal.dispose()
      terminalRef.current = null
      fitAddonRef.current = null
      writtenLengthRef.current = 0
    }
  }, [])

  useEffect(() => {
    const terminal = terminalRef.current
    if (terminal === null) {
      return
    }

    terminal.options.theme = createTerminalTheme(terminalBackground)
  }, [terminalBackground])

  // Handle session change and output updates
  useEffect(() => {
    const terminal = terminalRef.current
    const fitAddon = fitAddonRef.current
    if (terminal === null || fitAddon === null) {
      return
    }

    // If session has changed, clear and reset
    if (currentSessionKeyRef.current !== sessionKey) {
      terminal.clear()
      terminal.reset()
      writtenLengthRef.current = 0
      currentSessionKeyRef.current = sessionKey
      
      if (output.length > 0) {
        replayingRef.current = true
        terminal.write(stripReplayControlSequences(output))
        writtenLengthRef.current = output.length
        queueMicrotask(() => {
          replayingRef.current = false
        })
      }
      
      requestAnimationFrame(() => {
        fitAddon.fit()
        onResizeRef.current(terminal.cols, terminal.rows)
      })
      return
    }

    // If output is shorter than what we've written, the buffer was probably reset on the server
    if (output.length < writtenLengthRef.current) {
      terminal.clear()
      writtenLengthRef.current = 0
    }

    // Incremental write
    const nextChunk = output.slice(writtenLengthRef.current)
    if (nextChunk.length > 0) {
      terminal.write(nextChunk)
      writtenLengthRef.current = output.length
    }
  }, [sessionKey, output])

  return (
    <div
      ref={containerRef}
      className="relative m-2 mt-0 flex-1 overflow-hidden border border-white/10 p-3 text-ops-text shadow-[inset_0_1px_0_rgb(255_255_255/0.035)] focus:outline-none"
      style={{ backgroundColor: terminalBackground }}
      aria-label={t('terminal.session')}
      onMouseDown={() => {
        terminalRef.current?.focus()
      }}
      tabIndex={0}
    >
      <div ref={terminalHostRef} className="w-full h-full" />
    </div>
  )
}
