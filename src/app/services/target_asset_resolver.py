from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

from app.core.llm.types import LLMCompletionRequest, LLMMessage
from app.shared.schemas import ModelConfig


logger = logging.getLogger(__name__)


NETWORK_ASSET_TYPES = {"", "network", "cisco", "huawei", "juniper", "h3c"}
LINUX_ASSET_TYPES = {"linux"}

TargetAssetSelectionSource = Literal[
    "explicit_request",
    "prompt_named_assets",
    "prompt_asset_scope",
    "current_asset_default",
    "llm_unavailable_default",
]
TargetAssetSelectionConfidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class AssetSelectionCandidate:
    id: int
    name: str
    asset_type: str
    host: str
    group_name: str = ""
    tags: tuple[str, ...] = ()
    vendor: str = ""
    description: str = ""


@dataclass(frozen=True)
class TargetAssetSelection:
    asset_ids: list[int]
    source: TargetAssetSelectionSource
    reason: str
    confidence: TargetAssetSelectionConfidence = "medium"


class TargetAssetResolver:
    def resolve(
        self,
        *,
        prompt: str,
        current_asset_id: int | None,
        candidates: list[AssetSelectionCandidate],
        model_config: ModelConfig | None,
        explicit_asset_ids: list[int] | None = None,
    ) -> TargetAssetSelection:
        valid_ids = {candidate.id for candidate in candidates}
        if explicit_asset_ids:
            selected = [asset_id for asset_id in explicit_asset_ids if asset_id in valid_ids]
            if selected:
                return TargetAssetSelection(
                    asset_ids=selected,
                    source="explicit_request",
                    reason="请求体显式指定了目标资产。",
                    confidence="high",
                )

        deterministic_selection = self._resolve_deterministic(
            prompt=prompt,
            current_asset_id=current_asset_id,
            candidates=candidates,
        )
        if deterministic_selection.asset_ids:
            return deterministic_selection

        if model_config is not None:
            llm_selection = self._resolve_with_llm(
                prompt=prompt,
                current_asset_id=current_asset_id,
                candidates=candidates,
                model_config=model_config,
            )
            if llm_selection.asset_ids:
                return llm_selection

        if model_config is None:
            return TargetAssetSelection(
                asset_ids=[],
                source="prompt_asset_scope",
                reason="提示词没有命中确定性资产范围。",
                confidence="low",
            )

        if current_asset_id is not None and current_asset_id in valid_ids:
            return TargetAssetSelection(
                asset_ids=[current_asset_id],
                source="llm_unavailable_default",
                reason=f"未能从提示词解析出目标资产，默认使用当前资产 {current_asset_id}。",
                confidence="low",
            )

        return TargetAssetSelection(
            asset_ids=[],
            source="llm_unavailable_default",
            reason="未能从提示词解析出目标资产，且当前资产不可用。",
            confidence="low",
        )

    def _resolve_deterministic(
        self,
        *,
        prompt: str,
        current_asset_id: int | None,
        candidates: list[AssetSelectionCandidate],
    ) -> TargetAssetSelection:
        normalized = prompt.lower()
        scoped = self._resolve_clear_scope(normalized, candidates)
        if scoped.asset_ids:
            return scoped

        matched: list[int] = []
        for candidate in candidates:
            terms = [
                candidate.name,
                candidate.host,
                candidate.group_name,
                candidate.vendor,
                *candidate.tags,
            ]
            if any(term and term.lower() in normalized for term in terms):
                matched.append(candidate.id)
        if matched:
            return TargetAssetSelection(
                asset_ids=matched,
                source="prompt_named_assets",
                reason="提示词中直接匹配到资产名称、主机地址、分组、标签或厂商。",
                confidence="high",
            )

        if current_asset_id is not None and any(term in normalized for term in ["当前资产", "当前节点", "this asset", "current asset"]):
            valid_ids = {candidate.id for candidate in candidates}
            if current_asset_id in valid_ids:
                return TargetAssetSelection(
                    asset_ids=[current_asset_id],
                    source="current_asset_default",
                    reason="提示词明确要求当前资产。",
                    confidence="high",
                )

        return TargetAssetSelection(
            asset_ids=[],
            source="prompt_asset_scope",
            reason="提示词没有命中确定性资产范围。",
            confidence="low",
        )

    def _resolve_clear_scope(
        self,
        normalized_prompt: str,
        candidates: list[AssetSelectionCandidate],
    ) -> TargetAssetSelection:
        if any(
            term in normalized_prompt
            for term in ["所有网络设备", "全部网络设备", "所有交换机", "全部交换机", "network devices", "all switches"]
        ):
            asset_ids = [candidate.id for candidate in candidates if candidate.asset_type in NETWORK_ASSET_TYPES]
            if asset_ids:
                return TargetAssetSelection(
                    asset_ids=asset_ids,
                    source="prompt_asset_scope",
                    reason="提示词要求所有网络设备，已按资产类型筛选。",
                    confidence="high",
                )

        if any(term in normalized_prompt for term in ["所有linux", "全部linux", "所有 linux", "全部 linux", "linux servers"]):
            asset_ids = [candidate.id for candidate in candidates if candidate.asset_type in LINUX_ASSET_TYPES]
            if asset_ids:
                return TargetAssetSelection(
                    asset_ids=asset_ids,
                    source="prompt_asset_scope",
                    reason="提示词要求所有 Linux 服务器，已按资产类型筛选。",
                    confidence="high",
                )

        return TargetAssetSelection(
            asset_ids=[],
            source="prompt_asset_scope",
            reason="提示词没有命中确定性资产范围。",
            confidence="low",
        )

    def _resolve_with_llm(
        self,
        *,
        prompt: str,
        current_asset_id: int | None,
        candidates: list[AssetSelectionCandidate],
        model_config: ModelConfig,
    ) -> TargetAssetSelection:
        valid_ids = {candidate.id for candidate in candidates}
        if not candidates:
            return TargetAssetSelection(
                asset_ids=[],
                source="llm_unavailable_default",
                reason="资产目录为空。",
                confidence="low",
            )

        try:
            from app.core.llm.factory import build_llm_provider

            provider = build_llm_provider(model_config)
            response = provider.complete(
                config=model_config,
                request=LLMCompletionRequest(
                    messages=[
                        LLMMessage(
                            role="system",
                            content=(
                                "你是运维任务的目标资产选择器。根据用户提示词和资产目录选择应执行任务的资产。"
                                "只返回严格 JSON，不要 markdown，不要解释。"
                                "JSON 格式：{\"asset_ids\":[数字],\"source\":\"prompt_named_assets|prompt_asset_scope|current_asset_default\","
                                "\"reason\":\"中文原因\",\"confidence\":\"high|medium|low\"}。"
                                "如果用户点名资产、主机名、IP、分组、标签或厂商，选择匹配资产。"
                                "如果用户说所有网络设备、所有 Linux 服务器、某分组、某类设备，按资产目录筛选。"
                                "如果用户没有提及资产或范围，选择 current_asset_id。"
                                "禁止编造资产 ID；只能从资产目录里选择。"
                            ),
                        ),
                        LLMMessage(
                            role="user",
                            content=json.dumps(
                                {
                                    "prompt": prompt,
                                    "current_asset_id": current_asset_id,
                                    "assets": [self._candidate_payload(candidate) for candidate in candidates],
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ],
                    temperature=0,
                    max_tokens=512,
                    json_mode=True,
                ),
            )
            payload = json.loads((response.text or "").strip())
        except Exception:
            logger.warning("LLM target asset resolution failed", exc_info=True)
            return TargetAssetSelection(
                asset_ids=[],
                source="llm_unavailable_default",
                reason="LLM 目标资产解析失败。",
                confidence="low",
            )

        if not isinstance(payload, dict):
            return TargetAssetSelection(
                asset_ids=[],
                source="llm_unavailable_default",
                reason="LLM 目标资产解析返回格式无效。",
                confidence="low",
            )

        raw_ids = payload.get("asset_ids") or []
        selected: list[int] = []
        if isinstance(raw_ids, list):
            for raw_id in raw_ids:
                try:
                    asset_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if asset_id in valid_ids and asset_id not in selected:
                    selected.append(asset_id)

        source = str(payload.get("source") or "prompt_asset_scope")
        if source not in {"prompt_named_assets", "prompt_asset_scope", "current_asset_default"}:
            source = "prompt_asset_scope"

        confidence = str(payload.get("confidence") or "medium")
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"

        return TargetAssetSelection(
            asset_ids=selected,
            source=cast(TargetAssetSelectionSource, source),
            reason=str(payload.get("reason") or "LLM 根据提示词和资产目录选择目标资产。"),
            confidence=cast(TargetAssetSelectionConfidence, confidence),
        )

    def _candidate_payload(self, candidate: AssetSelectionCandidate) -> dict[str, Any]:
        return {
            "asset_id": candidate.id,
            "name": candidate.name,
            "asset_type": candidate.asset_type,
            "host": candidate.host,
            "group_name": candidate.group_name,
            "tags": list(candidate.tags),
            "vendor": candidate.vendor,
            "description": candidate.description,
        }


def candidate_from_asset(asset: Any, *, group_name: str = "") -> AssetSelectionCandidate | None:
    asset_id = getattr(asset, "id", None)
    if asset_id is None:
        return None
    tags_value = str(getattr(asset, "tags", "") or "")
    return AssetSelectionCandidate(
        id=int(asset_id),
        name=str(getattr(asset, "name", "") or ""),
        asset_type=str(getattr(asset, "asset_type", "") or ""),
        host=str(getattr(asset, "host", "") or ""),
        group_name=group_name,
        tags=tuple(tag.strip() for tag in tags_value.split(",") if tag.strip()),
        vendor=str(getattr(asset, "vendor", "") or ""),
        description=str(getattr(asset, "description", "") or ""),
    )
