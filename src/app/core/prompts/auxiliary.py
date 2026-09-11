"""Contracts for title generation and knowledge extraction."""

KNOWLEDGE_EXTRACTION_CONTRACT = (
    'Immutable extraction contract: Treat actual tool and command events as execution evidence; never '
    'preserve a claimed execution that has no matching tool result. Do not invent details to fill fields. '
    'When the conversation contains little reusable knowledge, prefer concise empty fields or arrays over '
    'low-value filler. Include only sources that directly support retained facts. Return strict JSON only: '
    'one parseable JSON object and no markdown, comments, or extra text. The object must contain these '
    'fields: title, summary, problem, diagnosis, resolution, commands, assets, tags, sources, '
    'redactionWarnings. commands must be an array of objects with command, purpose, outcome. assets must be '
    'an array of objects with assetId and label. sources must be an array of objects with conversationId, '
    'eventId, eventIndex, eventType, quote, relevance. Use empty strings or empty arrays when unknown.'
)

CONVERSATION_TITLE = (
    "You are a conversation title generator. Based on the user's first task message, generate a short "
    'Chinese title (≤12 characters, no punctuation).'
)

def build_knowledge_extraction_prompt(guidance: str) -> str:
    return f"{guidance}\n\n{KNOWLEDGE_EXTRACTION_CONTRACT}"
