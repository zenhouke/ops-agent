import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/@xterm/') || id.includes('/node_modules/xterm/')) {
            return 'terminal-vendor'
          }
          if (id.includes('/node_modules/react') || id.includes('/node_modules/react-resizable-panels/')) {
            return 'react-vendor'
          }
          return undefined
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
