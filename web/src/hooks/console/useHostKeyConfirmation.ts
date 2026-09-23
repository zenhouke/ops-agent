import { useCallback, useEffect, useRef, useState } from 'react'
import { confirmTerminalHostKey, type HostKeyChallenge } from '../../api/terminal'

type PendingConfirmation = {
  challenge: HostKeyChallenge
  resolve: (confirmed: boolean) => void
}

export function useHostKeyConfirmation() {
  const [pending, setPending] = useState<PendingConfirmation[]>([])
  const pendingRef = useRef<PendingConfirmation[]>([])
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      pendingRef.current.forEach((item) => item.resolve(false))
      pendingRef.current = []
    }
  }, [])

  const answerHostKey = useCallback((confirmed: boolean) => {
    const [current, ...remaining] = pendingRef.current
    pendingRef.current = remaining
    setPending(remaining)
    current?.resolve(confirmed)
  }, [])

  const withHostKeyConfirmation = useCallback(async <T extends { host_key?: HostKeyChallenge | null },>(
    assetId: number | null,
    connect: () => Promise<T>,
  ): Promise<T> => {
    // A proxy and its destination can each require a separate confirmation.
    for (let attempt = 0; attempt < 8; attempt++) {
      const result = await connect()
      if (!result.host_key) return result
      const challenge = result.host_key
      if (!mounted.current) throw new Error('连接已取消')
      const confirmed = await new Promise<boolean>((resolve) => {
        pendingRef.current = [...pendingRef.current, { challenge, resolve }]
        setPending(pendingRef.current)
      })
      if (!confirmed) throw new Error('已取消主机信任，未建立连接')
      await confirmTerminalHostKey(assetId, challenge.token)
    }
    throw new Error('主机指纹确认次数过多，请检查代理配置后重试')
  }, [])

  return { hostKeyChallenge: pending[0]?.challenge ?? null, answerHostKey, withHostKeyConfirmation }
}
