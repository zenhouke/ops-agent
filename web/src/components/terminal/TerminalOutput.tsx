import { useEffect, useRef } from 'react'
import { useAppearance } from '../../hooks/useAppearance'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal, type ITheme } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'

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

const darkTerminalTheme: ITheme = {
  background: 'rgb(11, 15, 25)',
  foreground: 'rgb(241, 245, 249)',
  cursor: 'rgb(var(--ops-cyan))',
  selectionBackground: 'rgb(var(--ops-cyan) / 0.3)',
  black: 'rgb(30, 41, 59)',
  red: 'rgb(var(--ops-danger))',
  green: 'rgb(var(--ops-green))',
  yellow: 'rgb(var(--ops-warning))',
  blue: 'rgb(59, 130, 246)',
  magenta: 'rgb(139, 92, 246)',
  cyan: 'rgb(var(--ops-cyan))',
  white: 'rgb(241, 245, 249)',
  brightBlack: 'rgb(71, 85, 105)',
  brightRed: 'rgb(248, 113, 113)',
  brightGreen: 'rgb(52, 211, 153)',
  brightYellow: 'rgb(251, 191, 36)',
  brightBlue: 'rgb(96, 165, 250)',
  brightMagenta: 'rgb(167, 139, 250)',
  brightCyan: 'rgb(34, 211, 238)',
  brightWhite: 'rgb(255, 255, 255)',
}

const lightTerminalTheme: ITheme = {
  background: 'rgb(2, 6, 23)',
  foreground: 'rgb(226, 232, 240)',
  cursor: 'rgb(var(--ops-cyan))',
  selectionBackground: 'rgb(var(--ops-cyan) / 0.22)',
  black: 'rgb(15, 23, 42)',
  red: 'rgb(var(--ops-danger))',
  green: 'rgb(var(--ops-green))',
  yellow: 'rgb(var(--ops-warning))',
  blue: 'rgb(37, 99, 235)',
  magenta: 'rgb(124, 58, 237)',
  cyan: 'rgb(var(--ops-cyan))',
  white: 'rgb(248, 250, 252)',
  brightBlack: 'rgb(100, 116, 139)',
  brightRed: 'rgb(220, 38, 38)',
  brightGreen: 'rgb(5, 150, 105)',
  brightYellow: 'rgb(217, 119, 6)',
  brightBlue: 'rgb(29, 78, 216)',
  brightMagenta: 'rgb(109, 40, 217)',
  brightCyan: 'rgb(8, 145, 178)',
  brightWhite: 'rgb(255, 255, 255)',
}

export function TerminalOutput({ sessionKey, output, onInput, onResize }: TerminalOutputProps) {
  const { t, resolvedTheme } = useAppearance()
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
  const resolvedThemeRef = useRef(resolvedTheme)

  useEffect(() => {
    onInputRef.current = onInput
    onResizeRef.current = onResize
    outputRef.current = output
    sessionKeyRef.current = sessionKey
    resolvedThemeRef.current = resolvedTheme
  }, [onInput, onResize, output, sessionKey, resolvedTheme])

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
      theme: resolvedThemeRef.current === 'light' ? lightTerminalTheme : darkTerminalTheme,
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

    terminal.options.theme = resolvedTheme === 'light' ? lightTerminalTheme : darkTerminalTheme
  }, [resolvedTheme])

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
      className="relative flex-1 w-full overflow-hidden bg-slate-950 p-3 text-slate-100 shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] focus:outline-none dark:bg-ops-deep dark:text-ops-text"
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