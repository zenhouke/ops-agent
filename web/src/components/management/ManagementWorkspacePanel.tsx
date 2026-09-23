import { lazy, Suspense } from 'react'

import type { Asset, AssetGroup, ConversationContextStatus, SSHKey } from '../../types/ops'
import type { KnowledgeBaseController } from '../../hooks/useKnowledgeBase'
import { LoadingState } from '../layout/LoadingState'

const CredentialsWorkspace = lazy(() => import('./CredentialsWorkspace').then((module) => ({ default: module.CredentialsWorkspace })))
const AutomationWorkspace = lazy(() => import('./AutomationWorkspace').then((module) => ({ default: module.AutomationWorkspace })))
const ExtensionsWorkspace = lazy(() => import('./ExtensionsWorkspace').then((module) => ({ default: module.ExtensionsWorkspace })))
const GroupsWorkspace = lazy(() => import('./GroupsWorkspace').then((module) => ({ default: module.GroupsWorkspace })))
const KnowledgeWorkspace = lazy(() => import('../knowledge/KnowledgeWorkspace').then((module) => ({ default: module.KnowledgeWorkspace })))
const NetworkTopologyWorkspace = lazy(() => import('./NetworkTopologyWorkspace').then((module) => ({ default: module.NetworkTopologyWorkspace })))

export type ManagementWorkspace = 'knowledge' | 'topology' | 'credentials' | 'automation' | 'extensions' | 'groups'

type ManagementWorkspacePanelProps = {
  workspace: ManagementWorkspace
  loadingMessage: string
  assets: Asset[]
  groups: AssetGroup[]
  sshKeys: SSHKey[]
  conversationId: string | null
  conversationTitle: string
  selectedModel: string
  contextStatus: ConversationContextStatus | null
  knowledge: KnowledgeBaseController
  onOpenConversation: (conversationId: string) => void
  onOpenAsset: (assetId: number, action: 'terminal' | 'diagnose') => void
  onGroupsChange: (groups: AssetGroup[]) => void
  onSSHKeysChange: (sshKeys: SSHKey[]) => void
}

export function ManagementWorkspacePanel({
  workspace,
  loadingMessage,
  assets,
  groups,
  sshKeys,
  conversationId,
  conversationTitle,
  selectedModel,
  knowledge,
  onOpenConversation,
  onOpenAsset,
  onGroupsChange,
  onSSHKeysChange,
}: ManagementWorkspacePanelProps) {
  return (
    <Suspense fallback={<LoadingState message={loadingMessage} />}>
      {workspace === 'knowledge' ? (
        <KnowledgeWorkspace
          conversationId={conversationId}
          conversationTitle={conversationTitle}
          selectedModel={selectedModel}
          knowledge={knowledge}
          onOpenConversation={onOpenConversation}
        />
      ) : workspace === 'topology' ? (
        <NetworkTopologyWorkspace assets={assets} onOpenAsset={onOpenAsset} />
      ) : workspace === 'credentials' ? (
        <CredentialsWorkspace initialSSHKeys={sshKeys} onSSHKeysChange={onSSHKeysChange} />
      ) : workspace === 'automation' ? (
        <AutomationWorkspace assets={assets} onOpenConversation={onOpenConversation} />
      ) : workspace === 'extensions' ? (
        <ExtensionsWorkspace />
      ) : (
        <GroupsWorkspace groups={groups} onGroupsChange={onGroupsChange} />
      )}
    </Suspense>
  )
}
