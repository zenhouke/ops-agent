import React from 'react'
import ReactDOM from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import { App } from './App'
import { AppearanceProvider } from './hooks/useAppearance'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ThemeProvider
    attribute="data-theme"
    defaultTheme="system"
    enableSystem
    disableTransitionOnChange
    storageKey="ops-agent-theme-mode"
  >
    <AppearanceProvider>
      <App />
    </AppearanceProvider>
  </ThemeProvider>,
)
