import { getDesktopApiAccessToken, getDesktopApiBaseUrl } from '../desktop'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const API_TOKEN_STORAGE_KEY = 'ops-agent:api-token'
let runtimeApiBaseUrl: string | null = null

export function getApiAccessToken(): string {
  return getDesktopApiAccessToken() || sessionStorage.getItem(API_TOKEN_STORAGE_KEY) || ''
}

export function setApiAccessToken(token: string | null): void {
  if (token) {
    sessionStorage.setItem(API_TOKEN_STORAGE_KEY, token)
  } else {
    sessionStorage.removeItem(API_TOKEN_STORAGE_KEY)
  }
}

async function resolveApiBaseUrl() {
  if (runtimeApiBaseUrl !== null) {
    return runtimeApiBaseUrl
  }
  const desktopBaseUrl = await getDesktopApiBaseUrl()
  if (desktopBaseUrl) {
    runtimeApiBaseUrl = desktopBaseUrl
    return desktopBaseUrl
  }
  return API_BASE_URL
}

async function buildRequest(path: string, init?: RequestInit) {
  const baseUrl = await resolveApiBaseUrl()
  const accessToken = getApiAccessToken()
  return fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(init?.headers ?? {}),
    },
  })
}

export async function getAuthenticationStatus(): Promise<{ required: boolean }> {
  const response = await buildRequest('/api/auth/status')
  if (!response.ok) throw new Error(await getErrorMessage(response))
  return (await response.json()) as { required: boolean }
}

export async function verifyApiAccessToken(): Promise<void> {
  const response = await buildRequest('/api/auth/verify', { method: 'POST' })
  if (!response.ok) throw new Error(await getErrorMessage(response))
}

async function getErrorMessage(response: Response) {
  const fallback = `Request failed: ${response.status}`
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown }
    if (typeof payload.detail === 'string') {
      return payload.detail
    }
    if (payload.detail && typeof payload.detail === 'object') {
      const detail = payload.detail as { failureReason?: unknown; status?: unknown }
      if (typeof detail.failureReason === 'string') {
        return detail.failureReason
      }
      if (typeof detail.status === 'string') {
        return detail.status
      }
    }
    if (typeof payload.message === 'string') {
      return payload.message
    }
  } catch {
    return fallback
  }
  return fallback
}

export async function requestEventStream(path: string, init?: RequestInit): Promise<Response> {
  const response = await buildRequest(path, {
    ...init,
    headers: {
      Accept: 'text/event-stream',
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return response
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await buildRequest(path, init)

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  return (await response.json()) as T
}

export async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const response = await buildRequest(path, init)

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }
}
