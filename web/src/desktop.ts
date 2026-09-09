type TauriCoreModule = {
  invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>
}

type DesktopBackendConfig = {
  baseUrl: string
  accessToken: string
}

let backendConfig: DesktopBackendConfig | null = null

export function getDesktopApiAccessToken(): string {
  return backendConfig?.accessToken ?? ''
}

export async function getDesktopApiBaseUrl(): Promise<string | null> {
  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  if (!isTauri) {
    return null
  }
  try {
    if (backendConfig) {
      return backendConfig.baseUrl
    }
    const tauriCore = (await import('@tauri-apps/api/core')) as TauriCoreModule
    const value = await tauriCore.invoke('backend_config')
    if (!value || typeof value !== 'object') {
      return null
    }
    const candidate = value as Partial<DesktopBackendConfig>
    if (typeof candidate.baseUrl !== 'string' || typeof candidate.accessToken !== 'string') {
      return null
    }
    backendConfig = { baseUrl: candidate.baseUrl, accessToken: candidate.accessToken }
    return backendConfig.baseUrl
  } catch {
    return null
  }
}
