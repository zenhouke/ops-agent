from __future__ import annotations

import sqlite3
from array import array
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, UTC
from pathlib import Path

from app.services.knowledge_models import (
    KnowledgeEntry,
    KnowledgeReindexResult,
    KnowledgeSearchFilters,
    KnowledgeSearchHit,
)

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


class KnowledgeSearchIndex:
    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def index_entry(self, entry: KnowledgeEntry, embedding: list[float]) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("DELETE FROM knowledge_index WHERE entry_id = ?", (entry.id,))
                
                asset_ids = ",".join(str(asset.asset_id) for asset in entry.assets if asset.asset_id is not None)
                tags = ",".join(entry.tags)
                
                connection.execute(
                    """
                    INSERT INTO knowledge_index (
                        entry_id, title, updated_at, source_conversation_id, asset_ids, tags, embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.title,
                        entry.updated_at,
                        entry.source_conversation.id,
                        asset_ids,
                        tags,
                        array('f', embedding).tobytes(),
                    ),
                )

    def delete_entry(self, entry_id: str) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("DELETE FROM knowledge_index WHERE entry_id = ?", (entry_id,))

    def rebuild(self, entries: Iterable[KnowledgeEntry]) -> KnowledgeReindexResult:
        indexed = 0
        failed = 0
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("DELETE FROM knowledge_index")
                for entry in entries:
                    if not entry.embedding:
                        # Skip if there's no embedding stored in the JSON document
                        failed += 1
                        continue
                    savepoint = f"entry_{indexed + failed}"
                    connection.execute(f"SAVEPOINT {savepoint}")
                    try:
                        asset_ids = ",".join(str(asset.asset_id) for asset in entry.assets if asset.asset_id is not None)
                        tags = ",".join(entry.tags)
                        connection.execute(
                            """
                            INSERT INTO knowledge_index (
                                entry_id, title, updated_at, source_conversation_id, asset_ids, tags, embedding
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                entry.id,
                                entry.title,
                                entry.updated_at,
                                entry.source_conversation.id,
                                asset_ids,
                                tags,
                                array('f', entry.embedding).tobytes(),
                            ),
                        )
                    except Exception:
                        connection.execute(f"ROLLBACK TO {savepoint}")
                        connection.execute(f"RELEASE {savepoint}")
                        failed += 1
                    else:
                        connection.execute(f"RELEASE {savepoint}")
                        indexed += 1
        return KnowledgeReindexResult(indexed=indexed, failed=failed)

    def search(self, query_embedding: list[float] | None, filters: KnowledgeSearchFilters) -> list[KnowledgeSearchHit]:
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            
            where_clauses = ["1 = 1"]
            params = []
            
            if filters.source_conversation_id is not None:
                where_clauses.append("source_conversation_id = ?")
                params.append(filters.source_conversation_id)
                
            sql = f"""
                SELECT entry_id, title, updated_at, source_conversation_id, asset_ids, tags, embedding
                FROM knowledge_index
                WHERE {' AND '.join(where_clauses)}
            """
            rows = connection.execute(sql, params).fetchall()
            
        candidates = []
        for row in rows:
            if filters.asset_id is not None:
                row_asset_ids = {int(x) for x in row["asset_ids"].split(",") if x.strip()}
                if filters.asset_id not in row_asset_ids:
                    continue
            if filters.tag:
                row_tags = {x.strip().lower() for x in row["tags"].split(",") if x.strip()}
                if filters.tag.strip().lower() not in row_tags:
                    continue
            candidates.append(row)
            
        hits = []
        for row in candidates:
            score = 0.0
            if query_embedding:
                try:
                    candidate_emb_bytes = row["embedding"]
                    candidate_emb = array('f')
                    candidate_emb.frombytes(candidate_emb_bytes)
                    candidate_emb_list = candidate_emb.tolist()
                    
                    dot_product = sum(a * b for a, b in zip(query_embedding, candidate_emb_list))
                    norm_a = sum(a * a for a in query_embedding) ** 0.5
                    norm_b = sum(b * b for b in candidate_emb_list) ** 0.5
                    if norm_a > 0 and norm_b > 0:
                        score = dot_product / (norm_a * norm_b)
                except Exception:
                    score = 0.0
            
            try:
                updated_at_str = row["updated_at"]
                dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                now = datetime.now(UTC)
                days_diff = max(0.0, (now - dt).total_seconds() / 86400.0)
                recency_boost = 1.0 / (1.0 + (days_diff / 30.0))
                score += recency_boost * 0.1
            except Exception:
                pass
                
            hits.append(KnowledgeSearchHit(entryId=str(row["entry_id"]), score=score))
            
        hits.sort(key=lambda hit: (-hit.score, hit.entry_id))
        
        offset = max(0, filters.offset)
        limit = _clamp_limit(filters.limit)
        return hits[offset : offset + limit]

    def count(self, filters: KnowledgeSearchFilters) -> int:
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            where_clauses = ["1 = 1"]
            params = []
            if filters.source_conversation_id is not None:
                where_clauses.append("source_conversation_id = ?")
                params.append(filters.source_conversation_id)
                
            sql = f"""
                SELECT asset_ids, tags
                FROM knowledge_index
                WHERE {' AND '.join(where_clauses)}
            """
            rows = connection.execute(sql, params).fetchall()
            
        count = 0
        for row in rows:
            if filters.asset_id is not None:
                row_asset_ids = {int(x) for x in row["asset_ids"].split(",") if x.strip()}
                if filters.asset_id not in row_asset_ids:
                    continue
            if filters.tag:
                row_tags = {x.strip().lower() for x in row["tags"].split(",") if x.strip()}
                if filters.tag.strip().lower() not in row_tags:
                    continue
            count += 1
        return count

    def _initialize_schema(self) -> None:
        try:
            with closing(self._connect()) as connection:
                with connection:
                    cursor = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_index_meta'"
                    )
                    if cursor.fetchone():
                        connection.execute("DROP TABLE IF EXISTS knowledge_fts")
                        connection.execute("DROP TABLE IF EXISTS knowledge_index_meta")
                        connection.execute("DROP TABLE IF EXISTS knowledge_index_assets")
                        connection.execute("DROP TABLE IF EXISTS knowledge_index_tags")

                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS knowledge_index (
                            entry_id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            source_conversation_id TEXT,
                            asset_ids TEXT NOT NULL,
                            tags TEXT NOT NULL,
                            embedding BLOB NOT NULL
                        )
                        """
                    )
        except sqlite3.OperationalError as exc:
            raise RuntimeError("Failed to initialize SQLite knowledge index database.") from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._index_path)


def _clamp_limit(limit: int) -> int:
    if limit <= 0:
        return _DEFAULT_LIMIT
    return min(limit, _MAX_LIMIT)
