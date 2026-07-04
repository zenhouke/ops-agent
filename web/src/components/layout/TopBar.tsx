import logoUrl from '../../public/logo.png'
import { useAppearance } from '../../hooks/useAppearance'
import { NotificationCenter } from './NotificationCenter'

type TopBarProps = {
  onOpenSettings?: () => void
  onOpenKnowledge?: () => void
  onToggleAssets?: () => void
  onToggleTerminal?: () => void
  assetsOpen?: boolean
  terminalOpen?: boolean
  terminalCount?: number
  assets?: Array<{ id: number; name: string }>
  onSelectConversation?: (conversationId: string) => void
  onSelectAsset?: (assetId: number) => void
}

export function TopBar({
  onOpenSettings,
  onOpenKnowledge,
  onToggleAssets,
  onToggleTerminal,
  assetsOpen = false,
  terminalOpen = false,
  terminalCount = 0,
  assets = [],
  onSelectConversation = () => {},
  onSelectAsset = () => {},
}: TopBarProps) {
  const { t } = useAppearance()

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-ops-border/15 bg-ops-bg px-4 z-50 dark:border-ops-border/20 dark:bg-ops-bg/50 dark:shadow-2xl">
      <div className="flex items-center gap-5">
        <img
          src={logoUrl}
          alt="Ops Agent"
          className="h-10 w-10 rounded-xl border border-ops-green/40 bg-ops-green/10 object-cover shadow-glow"
        />
        <div className="hidden sm:block">
          <h1 className="text-[14px] font-black text-ops-text leading-tight">{t('topBar.title')}</h1>
          <p className="text-[10px]  tracking-[0.2em] text-ops-muted/50 font-bold">{t('topBar.subtitle')}</p>
        </div>
      </div>
      <div className="flex items-center gap-3 sm:gap-6" aria-label="System status">
        {/* Assets drawer toggle */}
        {onToggleAssets ? (
          <button
            type="button"
            onClick={onToggleAssets}
            className={`flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-200 active:scale-95 ${
              assetsOpen
                ? 'bg-ops-green/15 text-ops-green'
                : 'text-ops-muted/60 hover:bg-ops-panel/40 hover:text-ops-text'
            }`}
            aria-label={t('topBar.toggleAssets')}
            title={t('topBar.toggleAssets')}
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="3" width="20" height="18" rx="2" />
              <path d="M9 3v18" />
            </svg>
          </button>
        ) : null}

        {/* Terminal drawer toggle */}
        {onToggleTerminal ? (
          <button
            type="button"
            onClick={onToggleTerminal}
            className={`relative flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-200 active:scale-95 ${
              terminalOpen
                ? 'bg-ops-green/15 text-ops-green'
                : 'text-ops-muted/60 hover:bg-ops-panel/40 hover:text-ops-text'
            }`}
            aria-label={t('topBar.toggleTerminal')}
            title={t('topBar.toggleTerminal')}
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m7 11 2-2-2-2" />
              <path d="M11 13h4" />
              <rect x="2" y="4" width="20" height="16" rx="2" />
            </svg>
            {terminalCount > 0 ? (
              <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-ops-green px-1 text-[8px] font-black text-ops-bg">
                {terminalCount}
              </span>
            ) : null}
          </button>
        ) : null}

        <button
          type="button"
          onClick={onOpenKnowledge}
          className="button inline-flex h-8 items-center gap-2 px-3 text-[10px] font-black tracking-[0.12em] active:scale-95"
          aria-label={t('topBar.knowledgeBase')}
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" />
          </svg>
          <span className="hidden sm:inline">{t('topBar.knowledgeBase')}</span>
        </button>
        <NotificationCenter
          assets={assets}
          onSelectConversation={onSelectConversation}
          onSelectAsset={onSelectAsset}
        />
        <button type="button" onClick={onOpenSettings} className="button flex h-8 w-8 items-center justify-center p-0 active:scale-95" aria-label={t('topBar.openSettings')}>
          <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.38.27.6.7.6 1.1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.9Z" />
          </svg>
        </button>
      </div>
    </header>
  )
}
