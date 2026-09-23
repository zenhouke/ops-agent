import { useEffect, useRef } from 'react'
import type { HostKeyChallenge } from '../../api/terminal'
import { useAppearance } from '../../hooks/useAppearance'

export function HostKeyConfirmDialog({ challenge, onAnswer }: {
  challenge: HostKeyChallenge
  onAnswer: (confirmed: boolean) => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const { language } = useAppearance()
  const zh = language === 'zh-CN'

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => {
      dialog?.close()
      previous?.focus()
    }
  }, [])

  return (
    <dialog ref={dialogRef} aria-labelledby="host-key-title"
      onCancel={(event) => { event.preventDefault(); onAnswer(false) }}
      className="m-auto w-[480px] max-w-[90vw] rounded-2xl border border-ops-border bg-ops-panel p-6 text-ops-text shadow-2xl backdrop:bg-black/60">
      <h2 id="host-key-title" className="text-lg font-semibold">
        {zh ? '确认 SSH 主机身份' : 'Confirm SSH host identity'}
      </h2>
      <p className="mt-3 text-sm text-ops-muted">
        {zh ? '首次连接此主机。请核对指纹，确认信任后将保存并继续连接。' : 'This host is new. Verify its fingerprint before saving it and continuing.'}
      </p>
      <dl className="my-5 space-y-3 rounded-lg border border-ops-border p-4 text-sm">
        <div><dt className="text-ops-muted">{zh ? '主机' : 'Host'}</dt><dd className="break-all font-mono">{challenge.hostname}</dd></div>
        <div><dt className="text-ops-muted">{zh ? '密钥类型' : 'Key type'}</dt><dd className="font-mono">{challenge.algorithm}</dd></div>
        <div><dt className="text-ops-muted">{zh ? '指纹' : 'Fingerprint'}</dt><dd className="break-all select-text font-mono">{challenge.fingerprint}</dd></div>
      </dl>
      <div className="flex justify-end gap-3">
        <button autoFocus type="button" className="button" onClick={() => onAnswer(false)}>{zh ? '取消' : 'Cancel'}</button>
        <button type="button" className="button button-primary" onClick={() => onAnswer(true)}>{zh ? '信任并连接' : 'Trust and connect'}</button>
      </div>
    </dialog>
  )
}
