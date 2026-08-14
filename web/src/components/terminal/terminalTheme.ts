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

  return {
    background,
    foreground,
    cursor: foreground,
    cursorAccent: background,
    selectionBackground: rgba(foreground, lightBackground ? 0.18 : 0.28),
    black: lightBackground ? '#343432' : '#1E1E1D',
    red: '#B24444',
    green: '#4A6A52',
    yellow: '#B07830',
    blue: '#6F6D68',
    magenta: '#817B78',
    cyan: '#5F5E5A',
    white: lightBackground ? '#4B4A47' : '#D8D7D3',
    brightBlack: '#73716C',
    brightRed: '#D46767',
    brightGreen: '#789782',
    brightYellow: '#C99A5B',
    brightBlue: '#97948E',
    brightMagenta: '#A49B98',
    brightCyan: '#A9A7A1',
    brightWhite: lightBackground ? '#202020' : '#FAF9F7',
  }
}
