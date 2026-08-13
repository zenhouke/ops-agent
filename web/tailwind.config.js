/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        ops: {
          bg: 'rgb(var(--ops-bg) / <alpha-value>)',
          panel: 'rgb(var(--ops-panel) / <alpha-value>)',
          strong: 'rgb(var(--ops-strong) / <alpha-value>)',
          deep: 'rgb(var(--ops-deep) / <alpha-value>)',
          border: 'rgb(var(--ops-border) / <alpha-value>)',
          text: 'rgb(var(--ops-text) / <alpha-value>)',
          muted: 'rgb(var(--ops-muted) / <alpha-value>)',
          green: 'rgb(var(--ops-green) / <alpha-value>)',
          cyan: 'rgb(var(--ops-cyan) / <alpha-value>)',
          warning: 'rgb(var(--ops-warning) / <alpha-value>)',
          danger: 'rgb(var(--ops-danger) / <alpha-value>)',
        },
      },
      boxShadow: {
        glass: '0 8px 32px 0 rgba(0, 0, 0, 0.37), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
        glow: '0 0 18px rgba(241, 245, 249, 0.16)',
        input: '0 4px 24px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
      },
      backgroundImage: {
        'ops-landscape': "radial-gradient(circle at top, rgba(255, 255, 255, 0.04), transparent 30%), linear-gradient(to bottom, #151515, #0A0A0A)",
      },
    },
  },
  plugins: [],
}
