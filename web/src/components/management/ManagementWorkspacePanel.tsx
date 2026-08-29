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
  contextStatus,
  knowledge,
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
          draft={knowledge.draft}
          draftSourceConversation={knowledge.draftSourceConversation}
          draftLoading={knowledge.draftLoading}
          draftError={knowledge.draftError}
          saving={knowledge.saving}
          entries={knowledge.entries}
          total={knowledge.total}
          limit={knowledge.limit}
          offset={knowledge.offset}
          loading={knowledge.loading}
          error={knowledge.error}
          reindexing={knowledge.reindexing}
          knowledgeEntriesInjected={contextStatus?.knowledgeEntriesInjected}
          knowledgeContextChars={contextStatus?.knowledgeContextChars}
          onSearch={knowledge.search}
          onDeleteEntry={knowledge.deleteEntry}
          onReindex={knowledge.reindex}
          onGenerateDraft={knowledge.generateDraft}
          onSaveDraft={knowledge.saveDraft}
          onClearDraft={knowledge.clearDraft}
          onDraftChange={knowledge.setDraft}
        />
      ) : workspace === 'topology' ? (
        <NetworkTopologyWorkspace assets={assets} />
      ) : workspace === 'credentials' ? (
        <CredentialsWorkspace initialSSHKeys={sshKeys} onSSHKeysChange={onSSHKeysChange} />
      ) : workspace === 'automation' ? (
        <AutomationWorkspace assets={assets} />
      ) : workspace === 'extensions' ? (
        <ExtensionsWorkspace />
      ) : (
        <GroupsWorkspace groups={groups} onGroupsChange={onGroupsChange} />
      )}
    </Suspense>
  )
}
