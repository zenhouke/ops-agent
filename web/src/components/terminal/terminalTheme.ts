import type { ITheme } from '@xterm/xterm'

function hexToRgb(color: string): [number, number, number] {
  return [
    Number.parseInt(color.slice(1, 3), 16),
    Number.parseInt(color.slice(3, 5), 16),
    Number.parseInt(color.slice(5, 7), 16),
  ]
}

function relativeLuminance([red, green, blue]: [number, number, number]) {
  const channels = [red, green, blue].map((channel) => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

function rgba(color: string, alpha: number) {
  const [red, green, blue] = hexToRgb(color)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

export function createTerminalTheme(background: string): ITheme {
  const lightBackground = relativeLuminance(hexToRgb(background)) > 0.45
  const foreground = lightBackground ? '#202020' : '#EEEDEA'
  const ansiColors = lightBackground
    ? {
        black: '#242424',
        red: '#C62828',
        green: '#2E7D32',
        yellow: '#9A6700',
        blue: '#1565C0',
        magenta: '#7B1FA2',
        cyan: '#00796B',
        white: '#5A5956',
        brightBlack: '#73716C',
        brightRed: '#D32F2F',
        brightGreen: '#388E3C',
        brightYellow: '#B26A00',
        brightBlue: '#1976D2',
        brightMagenta: '#8E24AA',
        brightCyan: '#00897B',
        brightWhite: '#202020',
      }
    : {
        black: '#242424',
        red: '#F07178',
        green: '#AAD94C',
        yellow: '#FFB454',
        blue: '#59C2FF',
        magenta: '#D2A6FF',
        cyan: '#95E6CB',
        white: '#D8D7D3',
        brightBlack: '#73716C',
        brightRed: '#FF8F88',
        brightGreen: '#C2E86B',
        brightYellow: '#FFD580',
        brightBlue: '#73D0FF',
        brightMagenta: '#DFBFFF',
        brightCyan: '#B8F3E2',
        brightWhite: '#FAF9F7',
      }

  return {
    background,
    foreground,
    cursor: foreground,
    cursorAccent: background,
    selectionBackground: rgba(foreground, lightBackground ? 0.18 : 0.28),
    ...ansiColors,
  }
}
