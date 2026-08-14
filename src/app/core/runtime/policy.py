def needs_approval(risk_level: str) -> bool:
    normalized = (risk_level or "low").strip().lower()
    return normalized in {"medium", "high"}
