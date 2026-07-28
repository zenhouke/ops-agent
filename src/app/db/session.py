from collections.abc import Generator

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.shared.config import APP_DIR, DB_PATH


APP_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_asset_columns()
    _ensure_model_usage_columns()
    _ensure_scheduler_columns()


def _ensure_asset_columns() -> None:
    inspector = inspect(engine)
    if "assets" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("assets")}
    with engine.begin() as connection:
        if "proxy_asset_id" not in existing:
            connection.execute(text("ALTER TABLE assets ADD COLUMN proxy_asset_id INTEGER"))


def _ensure_model_usage_columns() -> None:
    inspector = inspect(engine)
    if "model_usages" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("model_usages")}
    statements = {
        "runtime_id": "ALTER TABLE model_usages ADD COLUMN runtime_id VARCHAR NOT NULL DEFAULT ''",
        "conversation_id": "ALTER TABLE model_usages ADD COLUMN conversation_id VARCHAR NOT NULL DEFAULT ''",
        "input_tokens": "ALTER TABLE model_usages ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0",
        "output_tokens": "ALTER TABLE model_usages ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0",
        "cache_creation_input_tokens": "ALTER TABLE model_usages ADD COLUMN cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0",
        "cache_read_input_tokens": "ALTER TABLE model_usages ADD COLUMN cache_read_input_tokens INTEGER NOT NULL DEFAULT 0",
        "total_tokens": "ALTER TABLE model_usages ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0",
        "call_kind": "ALTER TABLE model_usages ADD COLUMN call_kind VARCHAR NOT NULL DEFAULT 'agent'",
    }
    with engine.begin() as connection:
        if "task_id" in existing:
            nullable = next((column.get("nullable", True) for column in inspector.get_columns("model_usages") if column["name"] == "task_id"), True)
            if nullable is False:
                connection.execute(text("ALTER TABLE model_usages RENAME TO model_usages_legacy"))
                SQLModel.metadata.create_all(engine)
                connection.execute(text("""
                    INSERT INTO model_usages (
                        task_id, model_config_id, provider, model_name, base_url_snapshot,
                        temperature_snapshot, max_tokens_snapshot, created_at
                    )
                    SELECT task_id, model_config_id, provider, model_name, base_url_snapshot,
                        temperature_snapshot, max_tokens_snapshot, created_at
                    FROM model_usages_legacy
                """))
                connection.execute(text("DROP TABLE model_usages_legacy"))
                return
        for column_name, statement in statements.items():
            if column_name not in existing:
                connection.execute(text(statement))


def _ensure_scheduler_columns() -> None:
    inspector = inspect(engine)
    if "scheduled_jobs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("scheduled_jobs")}
    statements = {
        "run_status": "ALTER TABLE scheduled_jobs ADD COLUMN run_status VARCHAR NOT NULL DEFAULT 'idle'",
        "lease_owner": "ALTER TABLE scheduled_jobs ADD COLUMN lease_owner VARCHAR NOT NULL DEFAULT ''",
        "lease_expires_at": "ALTER TABLE scheduled_jobs ADD COLUMN lease_expires_at DATETIME",
        "last_finished_at": "ALTER TABLE scheduled_jobs ADD COLUMN last_finished_at DATETIME",
        "last_error": "ALTER TABLE scheduled_jobs ADD COLUMN last_error VARCHAR NOT NULL DEFAULT ''",
    }
    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in existing:
                connection.execute(text(statement))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
