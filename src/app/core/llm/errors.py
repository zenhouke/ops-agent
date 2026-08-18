from __future__ import annotations


TLS_ROUTER_RESTRICTION = "only allows clients matched by the configured tls router"


def user_facing_llm_error(error: Exception) -> str:
    message = str(error).strip()
    normalized = message.lower()
    if TLS_ROUTER_RESTRICTION in normalized:
        return (
            "模型供应商拒绝了当前客户端（HTTP 403）：这把 API Key 仅允许其配置的 "
            "TLS Router 客户端，不能用于 Ops Agent 的通用 OpenAI 客户端。"
            "请在供应商控制台取消该 Key 的客户端限制，或换用允许 OpenAI-compatible/Responses 客户端的 Key。"
        )
    if "model is not found" in normalized or "model_not_found" in normalized:
        return "模型供应商未找到当前模型。请在模型设置中重新发现模型，并选择供应商实际提供的模型后重试。"
    if "insufficient_quota" in normalized or "quota exceeded" in normalized or "quota_exceeded" in normalized:
        return "模型供应商额度已用尽（HTTP 429）。请更换模型或补充供应商账户额度后重试。"
    if "concurrency limit" in normalized or "too many concurrent" in normalized:
        return "模型供应商并发额度已满。请等待当前请求结束后重试，或检查供应商账户的并发限制。"
    if "request timed out" in normalized or "timed out" in normalized or "timeout" in normalized:
        return "模型供应商响应超时。请检查供应商连接，或在模型设置中适当增加超时时间后重试。"
    if "authentication" in normalized or "invalid api key" in normalized or "incorrect api key" in normalized:
        return "模型供应商认证失败。请检查当前模型配置的 API Key。"
    if "response.failed" in normalized or "upstream_error" in normalized:
        return "模型供应商请求失败。请在模型设置中测试当前配置后重试。"
    return message or "Model provider request failed."
