import { useEffect, useState } from 'react'
import { createScheduledJob } from '../../api'
import { listJumpServerInstances, listJumpServerOrganizations, type JumpServerInstance, type JumpServerOrganization } from '../../api/jumpserver'
import { startOperation, operationActive } from '../../api/operations'
import { useOperations } from '../../hooks/useOperations'
import { OperationPanel } from '../operations/OperationPanel'

export function OrganizationInspection({ onOpenConversation }: { onOpenConversation: (id: string) => void }) {
  const [instances, setInstances] = useState<JumpServerInstance[]>([])
  const [instanceId, setInstanceId] = useState<number | null>(null)
  const [organizations, setOrganizations] = useState<JumpServerOrganization[]>([])
  const [organization, setOrganization] = useState<string | null>(null)
  const [prompt, setPrompt] = useState('请只读巡检设备健康状态、关键接口和系统告警，逐项给出检查证据。发现异常输出 [ALERT: 异常标题] 具体证据与建议；未发现异常输出 [OK]。不要修改配置。')
  const [interval, setInterval] = useState(86400)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const background = useOperations('inspection', instanceId ?? undefined, organization ?? undefined)
  useEffect(() => {
    let active = true
    void listJumpServerInstances().then((rows) => {
      if (!active) return
      const ssh = rows.filter((item) => item.enabled && item.authMode === 'ssh_gateway')
      setInstances(ssh); setInstanceId(ssh[0]?.id ?? null)
    }).catch((reason) => { if (active) setError(String(reason)) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    let active = true
    setOrganizations([]); setOrganization(null)
    if (instanceId !== null) void listJumpServerOrganizations(instanceId).then((rows) => {
      if (active) { setOrganizations(rows); setOrganization(rows[0]?.id ?? null) }
    }).catch((reason) => { if (active) setError(String(reason)) })
    return () => { active = false }
  }, [instanceId])
  const operations = background.operations.filter((op) => op.payload.instanceId === instanceId && op.payload.organization === organization)
  const run = async (scheduled: boolean) => {
    if (instanceId === null || organization === null) return
    setBusy(true); setError(''); setMessage('')
    try {
      if (scheduled) {
        await createScheduledJob({ name: `${organization || '未识别组织'} · 组织巡检`, asset_id: 0, instance_id: instanceId, organization, prompt, interval_seconds: interval, enabled: true })
        window.dispatchEvent(new Event('ops-agent:scheduler-changed'))
        setMessage('组织巡检计划已启用，将执行首次巡检；后续按间隔执行。新增组织资产会在下次巡检纳入。')
      } else {
        await startOperation({ kind: 'inspection', instanceId, organization, prompt })
        await background.refresh(); setMessage('巡检已在后台启动。涉及审批的设备请打开对应任务处理。')
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }
  return <section className="mb-6 space-y-3 rounded border border-ops-border/40 p-4 text-xs">
    <h3 className="font-semibold text-ops-text">组织批量巡检</h3>
    <p className="text-ops-muted">按组织逐台巡检并汇总结果。设备连接、命令执行仍经过现有授权和审批；等待审批的设备不会被计为巡检成功。</p>
    <div className="grid grid-cols-2 gap-3"><label>SSH 实例<select className="field-control mt-1 w-full" value={instanceId ?? ''} disabled={busy} onChange={(event) => { setInstanceId(event.target.value ? Number(event.target.value) : null); setOrganization(null) }}><option value="">请选择</option>{instances.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>组织<select className="field-control mt-1 w-full" value={organization === null ? '' : JSON.stringify(organization)} disabled={busy} onChange={(event) => setOrganization(event.target.value ? JSON.parse(event.target.value) as string : null)}><option value="">请选择</option>{organizations.map((item) => <option key={item.id} value={JSON.stringify(item.id)}>{item.name} · {item.assetCount} 台资产</option>)}</select></label></div>
    <label className="block">巡检要求<textarea className="field-control mt-1 min-h-24 w-full" value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={busy} /></label>
    <div className="flex flex-wrap items-center gap-2"><button className="button button-primary" disabled={busy || organization === null || !prompt.trim() || operations.some((op) => operationActive(op.status))} onClick={() => void run(false)}>立即巡检整个组织</button><label>执行间隔<select className="field-control ml-2" value={interval} onChange={(event) => setInterval(Number(event.target.value))}><option value={3600}>每小时</option><option value={43200}>每 12 小时</option><option value={86400}>每天</option></select></label><button className="button" disabled={busy || organization === null || !prompt.trim()} onClick={() => void run(true)}>创建并启用定时巡检</button></div>
    {message ? <p className="text-ops-cyan">{message}</p> : null}{error || background.error ? <p role="alert" className="text-ops-danger">{error || background.error}</p> : null}
    <h4 className="font-semibold">当前组织的巡检报告</h4>
    {operations.map((operation) => <OperationPanel key={operation.id} operation={operation} onRefresh={() => void background.refresh()} onOpenConversation={onOpenConversation} />)}
    {!operations.length ? <p className="text-ops-muted">暂无巡检记录。组织资产请在设置中同步。</p> : null}
  </section>
}
