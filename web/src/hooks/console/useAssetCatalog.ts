import { useCallback } from 'react'
import {
  createAsset,
  deleteAsset as deleteAssetApi,
  updateAsset as updateAssetApi,
} from '../../api'
import type { AssetPayload } from '../../api'
import type { ConsoleBootstrap } from '../../types/api'
import type { Asset, AssetGroup, SSHKey } from '../../types/ops'

interface UseAssetCatalogProps {
  bootstrap: ConsoleBootstrap
  setBootstrap: (bootstrap: ConsoleBootstrap) => void
  selectAsset: (assetId: number) => void
  removeTerminalTab: (assetId: number) => void
  setSelectedModel: (updater: string | ((prev: string) => string)) => void
}

export function useAssetCatalog({
  bootstrap,
  setBootstrap,
  selectAsset,
  removeTerminalTab,
  setSelectedModel,
}: UseAssetCatalogProps) {
  const addAsset = useCallback(
    async (payload: AssetPayload) => {
      const asset = await createAsset(payload)
      setBootstrap({
        ...bootstrap,
        assets: [asset, ...bootstrap.assets],
      })
      selectAsset(asset.id)
    },
    [bootstrap, setBootstrap, selectAsset]
  )

  const updateAsset = useCallback(
    async (assetId: number, payload: AssetPayload) => {
      const asset = await updateAssetApi(assetId, payload)
      setBootstrap({
        ...bootstrap,
        assets: bootstrap.assets.map((item) =>
          item.id === asset.id ? asset : item
        ),
      })
      selectAsset(asset.id)
      return asset
    },
    [bootstrap, setBootstrap, selectAsset]
  )

  const deleteAsset = useCallback(
    async (assetId: number) => {
      await deleteAssetApi(assetId)
      const nextAssets = bootstrap.assets.filter((item) => item.id !== assetId)
      setBootstrap({
        ...bootstrap,
        assets: nextAssets,
      })
      removeTerminalTab(assetId)
    },
    [bootstrap, setBootstrap, removeTerminalTab]
  )

  const replaceGroups = useCallback(
    (groups: AssetGroup[]) => {
      const groupIds = new Set(groups.map((group) => group.id))
      setBootstrap({
        ...bootstrap,
        groups,
        assets: bootstrap.assets.map((asset) =>
          asset.groupId !== null && !groupIds.has(asset.groupId)
            ? { ...asset, groupId: null }
            : asset
        ),
      })
    },
    [bootstrap, setBootstrap]
  )

  const replaceModelOptions = useCallback(
    (modelOptions: string[]) => {
      setBootstrap({
        ...bootstrap,
        modelOptions,
        modelConfigured: modelOptions.length > 0,
        modelConfigurationMessage: modelOptions.length > 0
          ? ''
          : 'LLM 模型未配置，请先在设置中添加并设为默认模型。',
      })
      setSelectedModel((currentModel: string) =>
        modelOptions.includes(currentModel) ? currentModel : modelOptions[0] ?? ''
      )
    },
    [bootstrap, setBootstrap, setSelectedModel]
  )

  const replaceSSHKeys = useCallback(
    (sshKeys: SSHKey[]) => {
      setBootstrap({
        ...bootstrap,
        sshKeys,
        assets: bootstrap.assets.map((asset) =>
          asset.sshKeyId !== null &&
          !sshKeys.some((sshKey) => sshKey.id === asset.sshKeyId)
            ? { ...asset, sshKeyId: null }
            : asset
        ),
      })
    },
    [bootstrap, setBootstrap]
  )

  return {
    addAsset,
    updateAsset,
    deleteAsset,
    replaceGroups,
    replaceModelOptions,
    replaceSSHKeys,
  }
}
