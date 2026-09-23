import { useAppearance } from '../../hooks/useAppearance'
import type { Asset } from '../../types/ops'
import { SchedulerSection } from '../settings/SchedulerSection'
import { OrganizationInspection } from './OrganizationInspection'
import { ManagementShell } from './ManagementShell'

export function AutomationWorkspace({ assets, onOpenConversation }: { assets: Asset[]; onOpenConversation: (id: string) => void }) {
  const { t } = useAppearance()
  return (
    <ManagementShell title={t('management.automation')} description={t('management.automationDescription')}>
      <OrganizationInspection onOpenConversation={onOpenConversation} />
      <SchedulerSection assets={assets} />
    </ManagementShell>
  )
}
