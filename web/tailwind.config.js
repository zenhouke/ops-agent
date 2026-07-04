import animate from 'tailwindcss-animate'

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
          emerald: 'rgb(var(--ops-green) / <alpha-value>)',
          // 保留 cyan 作为次级强调色（交互态/聚焦），主色由 emerald 承担
          cyan: 'rgb(var(--ops-cyan) / <alpha-value>)',
          warning: 'rgb(var(--ops-warning) / <alpha-value>)',
          danger: 'rgb(var(--ops-danger) / <alpha-value>)',
        },
      },
      boxShadow: {
        glass: '0 8px 32px 0 rgba(0, 0, 0, 0.37), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
        glow: '0 0 20px rgb(var(--ops-green) / 0.4)',
        'glow-cyan': '0 0 20px rgb(var(--ops-cyan) / 0.3)',
        input: '0 4px 24px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
      },
      backgroundImage: {
        'ops-landscape': "radial-gradient(circle at top, rgb(var(--ops-green) / 0.05), transparent 30%), linear-gradient(to bottom, rgb(var(--ops-panel)), rgb(var(--ops-bg)))",
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'fade-in-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.8' },
        },
        'aurora-shift': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(3%, -2%) scale(1.05)' },
          '66%': { transform: 'translate(-2%, 3%) scale(0.98)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'fade-in-up': 'fade-in-up 0.4s ease-out',
        'scale-in': 'scale-in 0.2s ease-out',
        'glow-pulse': 'glow-pulse 3s ease-in-out infinite',
        'aurora-shift': 'aurora-shift 20s ease-in-out infinite',
        shimmer: 'shimmer 2s infinite',
      },
    },
  },
  plugins: [animate],
}
