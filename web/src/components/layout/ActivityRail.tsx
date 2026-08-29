import { useAppearance } from '../../hooks/useAppearance'

export type WorkspaceSection = 'assets' | 'jumpserver' | 'conversations'
export type PrimaryWorkspace = WorkspaceSection | 'knowledge' | 'topology' | 'credentials' | 'automation' | 'extensions'

type ActivityRailProps = {
  activeWorkspace: PrimaryWorkspace
  onSelectWorkspace: (workspace: PrimaryWorkspace) => void
  onOpenSettings: () => void
}

type RailButtonProps = {
  active?: boolean
  label: string
  onClick: () => void
  children: React.ReactNode
}

function RailButton({ active = false, label, onClick, children }: RailButtonProps) {
  return (
    <button
      type="button"
      className={`activity-rail-button ${active ? 'activity-rail-button-active' : ''}`}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  )
}

export function ActivityRail({ activeWorkspace, onSelectWorkspace, onOpenSettings }: ActivityRailProps) {
  const { t } = useAppearance()

  return (
    <nav className="activity-rail" aria-label={t('management.workspaceNavigation')}>
      <div className="flex flex-col items-center gap-1 py-1.5">
        <RailButton active={activeWorkspace === 'assets'} label={t('assets.nodeAssets')} onClick={() => onSelectWorkspace('assets')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="6" rx="1.5" /><rect x="3" y="14" width="18" height="6" rx="1.5" /><path d="M7 7h.01M7 17h.01" /></svg>
        </RailButton>
        <RailButton active={activeWorkspace === 'jumpserver'} label={t('management.jumpServerAssets')} onClick={() => onSelectWorkspace('jumpserver')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v5H4zM4 14h16v5H4z" /><path d="M8 10v4M16 10v4M7 7h.01M7 16h.01" /></svg>
        </RailButton>
        <RailButton active={activeWorkspace === 'conversations'} label={t('assets.history')} onClick={() => onSelectWorkspace('conversations')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l3 3v15H6z" /><path d="M15 3v4h4M9 11h6M9 15h4" /></svg>
        </RailButton>
        <RailButton active={activeWorkspace === 'knowledge'} label={t('management.knowledge')} onClick={() => onSelectWorkspace('knowledge')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /></svg>
        </RailButton>
        <RailButton active={activeWorkspace === 'topology'} label="网络拓扑" onClick={() => onSelectWorkspace('topology')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="m7 11 10-4M7 13l10 4"/></svg>
        </RailButton>
      </div>

      <div className="mx-auto my-1 h-px w-5 bg-ops-border/35" aria-hidden="true" />

      <div className="flex flex-col items-center gap-1 py-1.5">
        <RailButton active={activeWorkspace === 'credentials'} label={t('management.credentials')} onClick={() => onSelectWorkspace('credentials')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4" /><path d="m11 12 8-8M15 8l2 2M17 6l2 2" /></svg>
        </RailButton>
        <RailButton active={activeWorkspace === 'automation'} label={t('management.automation')} onClick={() => onSelectWorkspace('automation')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2M8 2v3M16 2v3" /></svg>
        </RailButton>
        <RailButton active={activeWorkspace === 'extensions'} label={t('management.extensions')} onClick={() => onSelectWorkspace('extensions')}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3v4M16 3v4M5 7h14v4a7 7 0 0 1-14 0zM12 18v3" /></svg>
        </RailButton>
      </div>

      <div className="mt-auto flex flex-col items-center gap-1 border-t border-ops-border/25 py-1.5">
        <RailButton label={t('topBar.openSettings')} onClick={onOpenSettings}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06-.06A1.7 1.7 0 0 0 19.4 9c.38.27.6.7.6 1.1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.9Z" /></svg>
        </RailButton>
      </div>
    </nav>
  )
}
