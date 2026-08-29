import { type FormEvent, type ReactNode, useEffect, useState } from 'react'

import {
  getApiAccessToken,
  getAuthenticationStatus,
  setApiAccessToken,
  verifyApiAccessToken,
} from '../../api/client'

type AuthGateProps = {
  children: ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  const [authorized, setAuthorized] = useState(false)
  const [loading, setLoading] = useState(true)
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const status = await getAuthenticationStatus()
        if (!status.required) {
          if (active) setAuthorized(true)
          return
        }
        if (!getApiAccessToken()) return
        await verifyApiAccessToken()
        if (active) setAuthorized(true)
      } catch {
        setApiAccessToken(null)
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const nextToken = token.trim()
    if (!nextToken) return
    setError(null)
    setLoading(true)
    setApiAccessToken(nextToken)
    try {
      await verifyApiAccessToken()
      setAuthorized(true)
    } catch {
      setApiAccessToken(null)
      setError('访问令牌无效，请重试。')
    } finally {
      setLoading(false)
    }
  }

  if (authorized) return children

  return (
    <main className="flex min-h-screen items-center justify-center bg-ops-bg p-6">
      <form className="w-full max-w-sm rounded-2xl border border-ops-border bg-ops-panel p-6 shadow-2xl" onSubmit={submit}>
        <h1 className="text-lg font-semibold text-ops-text">Ops Agent 访问验证</h1>
        <p className="mt-2 text-sm text-ops-muted">请输入服务器配置的 API 访问令牌。</p>
        <label className="mt-5 block text-xs font-medium text-ops-muted" htmlFor="ops-agent-api-token">访问令牌</label>
        <input
          id="ops-agent-api-token"
          autoComplete="current-password"
          autoFocus
          className="mt-2 w-full rounded-lg border border-ops-border bg-ops-deep px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-cyan"
          disabled={loading}
          onChange={(event) => setToken(event.target.value)}
          type="password"
          value={token}
        />
        {error ? <p className="mt-3 text-xs text-ops-danger">{error}</p> : null}
        <button className="mt-5 w-full rounded-lg bg-ops-cyan px-4 py-2 text-sm font-semibold text-ops-deep disabled:opacity-50" disabled={loading || !token.trim()} type="submit">
          {loading ? '正在验证…' : '进入工作台'}
        </button>
      </form>
    </main>
  )
}
