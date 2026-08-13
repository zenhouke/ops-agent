import { useAppearance } from '../../hooks/useAppearance'
import type { Asset } from '../../types/ops'
import { SchedulerSection } from '../settings/SchedulerSection'
import { ManagementShell } from './ManagementShell'

export function AutomationWorkspace({ assets }: { assets: Asset[] }) {
  const { t } = useAppearance()
  return (
    <ManagementShell title={t('management.automation')} description={t('management.automationDescription')}>
      <SchedulerSection assets={assets} />
    </ManagementShell>
  )
}
