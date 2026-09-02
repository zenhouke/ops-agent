#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from pydantic import SecretStr
from sqlmodel import Session, create_engine, select

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.core.loop.message_manager import MessageManager
from app.core.loop.loop_state import LoopContext, LoopState
from app.core.loop.runtime_manager import LoopRuntimeManager
from app.core.loop.runtime_models import RuntimeTerminalAuthorization
from app.core.loop.state_machine import RuntimeStateTransitionError, transition_runtime_state
from app.core.tool.execute_command import ExecuteCommandHandler
from app.core.connectors.execution import ExecutionContext
from app.core.connectors.local_pty import LocalPtyConnector
from app.core.connectors.session_manager import TerminalSessionManager
from app.core.connectors.ssh_host_keys import configure_strict_ssh_client, strict_netmiko_options
from app.core.approval import ApprovalChecker, ApprovalContext, ApprovalPermissions, ApprovalPolicy, TrustedCommandRule
from app.db.models import AuditLog, ModelConfigRecord
import app.db.repositories.audit as audit_repository
import app.db.migrations as database_migrations
import app.api as api_module
from app.api.middleware.security import RequestLimitMiddleware, SecurityHeadersMiddleware
from app.services.approval_service import ApprovalService
import app.services.credential_migration_service as credential_migration
from app.services.runtime_store import interruption_recovery
from app.shared.enums import ModelProvider
from app.shared.schemas import ModelConfig


def scenario_text_stream_uses_deltas_and_final_snapshot() -> None:
    manager = MessageManager(runtime_id="eval-message-delta")
    events = [*manager.begin_message(message_type="say", say_type="text")]
    message_id = str(events[0].payload["id"])
    events.extend(manager.update(text="hello "))
    events.extend(manager.update(text="world"))
    events.extend(manager.finalize())

    assert [event.event_type for event in events] == [
        "message_update",
        "delta",
        "delta",
        "message_update",
    ]
    assert events[1].message_id == message_id
    assert events[1].payload["text"] == "hello "
    assert events[2].payload["text"] == "world"
    assert events[3].payload["text"] == "hello world"
    assert events[3].payload["partial"] is False


def scenario_event_window_gap_falls_back_to_durable_store() -> None:
    durable_events = [
        {"id": f"event-{sequence}", "kind": "delta", "sequence": sequence}
        for sequence in range(2, 7)
    ]

    class Store:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def events_since(self, runtime_id: str, since: int):
            self.calls.append((runtime_id, since))
            return 6, [event for event in durable_events if event["sequence"] > since]

    store = Store()
    manager = LoopRuntimeManager(tools_factory=lambda _: [])
    manager._runtime_store = store  # type: ignore[assignment]
    manager._by_runtime["eval-window"] = SimpleNamespace(
        runtime_id="eval-window",
        conversation_id="eval-conversation",
        state=SimpleNamespace(phase="executing"),
        updated_at=datetime.now(UTC),
        events=deque(durable_events[-2:], maxlen=2),
        sequence=6,
        terminal_requests={},
    )

    latest, recovered = manager.events_since("eval-window", 1)
    assert latest == 6
    assert [event["sequence"] for event in recovered] == [2, 3, 4, 5, 6]
    assert store.calls == [("eval-window", 1)]

    latest, in_memory = manager.events_since("eval-window", 4)
    assert latest == 6
    assert [event["sequence"] for event in in_memory] == [5, 6]
    assert store.calls == [("eval-window", 1)]


def scenario_terminal_authorization_is_runtime_scoped() -> None:
    manager = LoopRuntimeManager(tools_factory=lambda _: [])
    now = datetime.now(UTC)
    authorization = RuntimeTerminalAuthorization(
        authorization_id="authorization-old",
        runtime_id="runtime-old",
        conversation_id="conversation-1",
        asset_id=1,
        asset_name="asset-1",
        terminal_id="terminal-1",
        source="initial_asset",
        approved_by="system",
        request_id=None,
        status="active",
        output_cursor=0,
        created_at=now,
        updated_at=now,
    )
    common = {
        "conversation_id": "conversation-1",
        "state": SimpleNamespace(phase="executing"),
        "updated_at": now,
        "events": deque(),
        "sequence": 0,
        "terminal_requests": {},
    }
    manager._by_runtime["runtime-old"] = SimpleNamespace(
        runtime_id="runtime-old",
        terminal_authorizations={authorization.authorization_id: authorization},
        **common,
    )
    manager._by_runtime["runtime-new"] = SimpleNamespace(
        runtime_id="runtime-new",
        terminal_authorizations={},
        **common,
    )
    manager._by_conversation["conversation-1"] = {
        "runtime-old": manager._by_runtime["runtime-old"],
        "runtime-new": manager._by_runtime["runtime-new"],
    }

    assert manager.resolve_terminal_authorization("runtime-old", authorization.authorization_id) is authorization
    try:
        manager.resolve_terminal_authorization("runtime-new", authorization.authorization_id)
    except ValueError as exc:
        assert str(exc) == "terminal authorization is not active"
    else:
        raise AssertionError("A terminal authorization from another runtime was accepted")


def scenario_command_scope_rechecks_asset_allowlist() -> None:
    state = SimpleNamespace(context=SimpleNamespace(
        asset_id=1,
        conversation_primary_asset_id=1,
        conversation_scope_mode="single",
        allowed_asset_ids=[1],
    ))
    assert ExecuteCommandHandler._scope_error(state, 1) is None
    assert "allowlist" in str(ExecuteCommandHandler._scope_error(state, 2))


def scenario_cancel_terminalizes_runtime_and_revokes_secrets() -> None:
    class Store:
        def save_snapshot(self, snapshot, *, run_state):
            _ = snapshot, run_state

        def append_event(self, snapshot, event, *, run_state):
            _ = snapshot, event, run_state

    manager = LoopRuntimeManager(tools_factory=lambda _: [])
    manager._runtime_store = Store()  # type: ignore[assignment]
    context = LoopContext(
        runtime_id="runtime-cancel",
        conversation_id="conversation-cancel",
        asset_id=1,
        asset_type="linux",
        terminal_id="terminal-1",
        asset_summary="asset-1",
        shell_type="bash",
        os_type="linux",
        user_prompt="run",
        model_config=ModelConfig(
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="runtime-eval",
            base_url="http://invalid",
            api_key=SecretStr("unused"),
        ),
        conversation_primary_asset_id=1,
        allowed_asset_ids=[1],
    )
    state = manager.create_runtime(
        conversation_id=context.conversation_id,
        asset_id=1,
        terminal_id="terminal-1",
        context=context,
    )
    state.pending_approval_token = "secret"
    state.pending_approval_token_hash = "hash"
    cancelled_execution_ids: list[str] = []
    session_manager = SimpleNamespace(
        cancel_execution=lambda execution_id: cancelled_execution_ids.append(execution_id)
    )
    terminal_service = SimpleNamespace(
        get_session=lambda terminal_id: session_manager if terminal_id == "terminal-1" else None
    )
    state.active_terminal_id = "terminal-1"
    state.active_execution_id = "execution-1"
    result = manager.cancel(context.runtime_id, terminal_service=terminal_service)
    snapshot = manager.get_snapshot(context.runtime_id)

    assert result["status"] == "failed"
    assert state.cancel_requested is True
    assert snapshot["run_state"] == "terminal"
    assert snapshot["pending_approval_token"] is None
    assert snapshot["error_message"] == "Cancelled by operator."
    assert cancelled_execution_ids == ["execution-1"]
    assert snapshot["active_terminal_id"] is None
    assert snapshot["active_execution_id"] is None


def scenario_runtime_state_machine_rejects_invalid_transitions() -> None:
    context = LoopContext(
        runtime_id="runtime-state-machine",
        conversation_id="conversation-state-machine",
        asset_id=1,
        asset_type="linux",
        terminal_id=None,
        asset_summary="asset-1",
        shell_type="bash",
        os_type="linux",
        user_prompt="run",
        model_config=ModelConfig(
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="runtime-eval",
            base_url="http://invalid",
            api_key=SecretStr("unused"),
        ),
    )
    state = LoopState(phase="executing", context=context)
    try:
        transition_runtime_state(state, "approving")
    except RuntimeStateTransitionError as exc:
        assert "pending_tool_call_id" in str(exc)
    else:
        raise AssertionError("Incomplete approval state was accepted")

    transition_runtime_state(state, "completed")
    try:
        transition_runtime_state(state, "executing")
    except RuntimeStateTransitionError as exc:
        assert "completed -> executing" in str(exc)
    else:
        raise AssertionError("Terminal runtime was resumed")


def scenario_local_execution_can_be_cancelled() -> None:
    connector = LocalPtyConnector()
    manager = TerminalSessionManager(connector)
    execution_id = "eval-cancellable-execution"
    worker = threading.Thread(
        target=lambda: manager.start_execution(
            "sleep 5",
            ExecutionContext(timeout_seconds=10),
            execution_id=execution_id,
        ),
        daemon=True,
    )
    started = time.monotonic()
    worker.start()
    deadline = time.monotonic() + 2
    while worker.is_alive() and not connector._execution_processes and time.monotonic() < deadline:
        time.sleep(0.01)
    manager.cancel_execution(execution_id)
    worker.join(timeout=2)
    assert not worker.is_alive()
    result = manager.get_execution_result(execution_id)
    assert result.completion_reason == "manual_stop"
    assert result.success is False
    assert time.monotonic() - started < 3


def scenario_interrupted_runtime_exposes_safe_recovery_action() -> None:
    assert interruption_recovery("approving") == ("restart_and_reapprove", "command_approval")
    assert interruption_recovery("waiting_user_input") == (
        "restart_with_operator_reply",
        "operator_input",
    )
    assert interruption_recovery("executing") == ("restart_from_conversation", "agent_execution")


def scenario_command_trust_is_exact_and_context_scoped() -> None:
    trusted = TrustedCommandRule(
        command="df -h",
        conversation_id="conversation-trusted",
        asset_id=42,
        profile="posix-shell",
    )
    checker = ApprovalChecker(ApprovalPolicy(
        permissions=ApprovalPermissions(deny=["rm -rf"]),
        trusted_commands=[trusted],
    ))
    context = ApprovalContext(
        conversation_id="conversation-trusted",
        asset_id=42,
        profile="posix-shell",
    )
    assert checker.check_command("df -h", context)[0] == "allow"
    for command in ("df", "df -h /", "df -h && id", "df -h; id", "df -h | cat", "df -h\nid"):
        assert checker.check_command(command, context)[0] == "ask", command
    assert checker.check_command("df -h", ApprovalContext(
        conversation_id="another-conversation",
        asset_id=42,
        profile="posix-shell",
    ))[0] == "ask"
    assert checker.check_command("df -h", ApprovalContext(
        conversation_id="conversation-trusted",
        asset_id=43,
        profile="posix-shell",
    ))[0] == "ask"
    assert checker.check_command("df -h", ApprovalContext(
        conversation_id="conversation-trusted",
        asset_id=42,
        profile="network-cli",
    ))[0] == "ask"
    assert checker.check_command("rm -rf /tmp/example", context)[0] == "deny"


def scenario_legacy_global_allow_is_removed_atomically() -> None:
    with TemporaryDirectory(prefix="ops-agent-approval-eval-") as tmp:
        settings_path = Path(tmp) / "settings.json"
        settings_path.write_text(json.dumps({
            "unrelated": {"keep": True},
            "permissions": {"allow": ["df", "*"], "deny": ["rm -rf"]},
        }), encoding="utf-8")
        service = ApprovalService(str(settings_path))
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert service.get_policy_dict() == {"permissions": {"allow": [], "deny": ["rm -rf"]}}
        assert persisted["permissions"]["allow"] == []
        assert persisted["unrelated"] == {"keep": True}
        assert service.add_allow_prefix("df") is False
        assert service.add_allow_command("*", context=ApprovalContext(
            conversation_id="conversation",
            asset_id=1,
        )) is False
        if os.name != "nt":
            assert settings_path.stat().st_mode & 0o777 == 0o600


def scenario_audit_chain_serializes_concurrent_writers_and_detects_tampering() -> None:
    with TemporaryDirectory(prefix="ops-agent-audit-eval-") as tmp:
        engine = create_engine(
            f"sqlite:///{Path(tmp) / 'audit.db'}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        AuditLog.__table__.create(engine)
        original_secret_provider = audit_repository.get_ops_agent_secret_key
        audit_repository.get_ops_agent_secret_key = lambda: "audit-eval-secret"
        errors: list[Exception] = []

        def write_entry(index: int) -> None:
            try:
                with Session(engine) as session:
                    audit_repository.create_audit_log(
                        session,
                        action="eval.concurrent",
                        entity_type="runtime",
                        actor="evaluation",
                        entity_id=str(index),
                        details=json.dumps({"index": index}),
                    )
            except Exception as exc:
                errors.append(exc)

        try:
            workers = [threading.Thread(target=write_entry, args=(index,)) for index in range(16)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=10)
            assert all(not worker.is_alive() for worker in workers)
            assert errors == []
            with Session(engine) as session:
                assert audit_repository.verify_audit_chain(session) == (True, 16)
                row = session.exec(select(AuditLog).where(AuditLog.id == 8)).one()
                row.details = "tampered"
                session.add(row)
                session.commit()
                assert audit_repository.verify_audit_chain(session) == (False, 8)
        finally:
            audit_repository.get_ops_agent_secret_key = original_secret_provider
            engine.dispose()


def scenario_http_limits_and_security_headers_are_enforced() -> None:
    async def invoke(app, *, headers=(), chunks=()):
        queued = deque(
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        )
        if not queued:
            queued.append({"type": "http.request", "body": b"", "more_body": False})
        sent = []

        async def receive():
            return queued.popleft() if queued else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/eval",
            "raw_path": b"/api/eval",
            "query_string": b"",
            "headers": list(headers),
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 443),
        }
        await app(scope, receive, send)
        return sent

    received_bodies: list[bytes] = []

    async def endpoint(scope, receive, send):
        _ = scope
        request = await receive()
        received_bodies.append(request.get("body", b""))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limited = RequestLimitMiddleware(endpoint, max_body_bytes=4, max_concurrency=2)
    oversized_header = asyncio.run(invoke(
        limited,
        headers=((b"content-length", b"5"),),
    ))
    assert oversized_header[0]["status"] == 413
    oversized_stream = asyncio.run(invoke(limited, chunks=(b"12", b"345")))
    assert oversized_stream[0]["status"] == 413
    accepted = asyncio.run(invoke(limited, chunks=(b"12", b"34")))
    assert accepted[0]["status"] == 204
    assert received_bodies == [b"1234"]

    secured = SecurityHeadersMiddleware(endpoint)
    response = asyncio.run(invoke(secured))
    headers = dict(response[0]["headers"])
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert b"frame-ancestors 'none'" in headers[b"content-security-policy"]
    assert headers[b"cache-control"] == b"no-store"


def scenario_ssh_clients_reject_unknown_hosts() -> None:
    class Client:
        def __init__(self) -> None:
            self.loaded_system = False
            self.loaded_files: list[str] = []
            self.policy = None

        def load_system_host_keys(self) -> None:
            self.loaded_system = True

        def load_host_keys(self, path: str) -> None:
            self.loaded_files.append(path)

        def set_missing_host_key_policy(self, policy) -> None:
            self.policy = policy

    previous = os.environ.get("OPS_AGENT_KNOWN_HOSTS_FILE")
    try:
        with TemporaryDirectory(prefix="ops-agent-known-hosts-eval-") as tmp:
            known_hosts = Path(tmp) / "known_hosts"
            known_hosts.write_text("", encoding="utf-8")
            os.environ["OPS_AGENT_KNOWN_HOSTS_FILE"] = str(known_hosts)
            client = Client()
            configure_strict_ssh_client(client)
            assert client.loaded_system is True
            assert client.loaded_files == [str(known_hosts)]
            assert client.policy.__class__.__name__ == "RejectPolicy"
            assert strict_netmiko_options() == {
                "ssh_strict": True,
                "system_host_keys": True,
                "alt_host_keys": True,
                "alt_key_file": str(known_hosts),
            }
            os.environ["OPS_AGENT_KNOWN_HOSTS_FILE"] = str(Path(tmp) / "missing")
            try:
                configure_strict_ssh_client(Client())
            except ValueError as exc:
                assert "does not exist" in str(exc)
            else:
                raise AssertionError("A missing configured known_hosts file was accepted")
    finally:
        if previous is None:
            os.environ.pop("OPS_AGENT_KNOWN_HOSTS_FILE", None)
        else:
            os.environ["OPS_AGENT_KNOWN_HOSTS_FILE"] = previous


def scenario_database_backup_is_verified_before_restore() -> None:
    original_app_dir = database_migrations.APP_DIR
    original_db_path = database_migrations.DB_PATH
    try:
        with TemporaryDirectory(prefix="ops-agent-backup-eval-") as tmp:
            app_dir = Path(tmp) / "data"
            app_dir.mkdir()
            database_path = app_dir / "ops_agent.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE eval_data (value TEXT NOT NULL)")
                connection.execute("INSERT INTO eval_data VALUES ('preserved')")
            (app_dir / "secret.key").write_text("evaluation-secret", encoding="utf-8")
            database_migrations.APP_DIR = app_dir
            database_migrations.DB_PATH = database_path
            backup_dir = database_migrations.create_pre_migration_backup(1, 2)
            manifest = database_migrations.verify_backup(backup_dir)
            assert manifest["fromVersion"] == 1
            assert manifest["toVersion"] == 2
            assert set(manifest["files"]) == {"ops_agent.db", "secret.key"}
            with sqlite3.connect(backup_dir / "ops_agent.db") as connection:
                assert connection.execute("SELECT value FROM eval_data").fetchone() == ("preserved",)
            with (backup_dir / "ops_agent.db").open("ab") as handle:
                handle.write(b"tampered")
            try:
                database_migrations.verify_backup(backup_dir)
            except ValueError as exc:
                assert "checksum mismatch" in str(exc).lower()
            else:
                raise AssertionError("A modified database backup passed checksum verification")
    finally:
        database_migrations.APP_DIR = original_app_dir
        database_migrations.DB_PATH = original_db_path


def scenario_plaintext_model_key_migrates_to_encrypted_storage() -> None:
    original_settings_path = credential_migration.SETTINGS_PATH
    original_secret_provider = credential_migration.get_ops_agent_secret_key
    try:
        with TemporaryDirectory(prefix="ops-agent-model-migration-eval-") as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({
                "provider": "openai_compatible",
                "model_name": "evaluation-model",
                "base_url": "https://example.invalid/v1",
                "api_key": "legacy-key",
                "unrelated": "preserved",
            }), encoding="utf-8")
            engine = create_engine(f"sqlite:///{Path(tmp) / 'models.db'}")
            ModelConfigRecord.__table__.create(engine)
            credential_migration.SETTINGS_PATH = settings_path
            credential_migration.get_ops_agent_secret_key = lambda: "model-migration-evaluation-secret"
            with Session(engine) as session:
                assert credential_migration.migrate_legacy_model_settings(session) is True
                records = list(session.exec(select(ModelConfigRecord)).all())
                assert len(records) == 1
                assert records[0].encrypted_api_key != "legacy-key"
                assert "legacy-key" not in records[0].encrypted_api_key
            persisted = json.loads(settings_path.read_text(encoding="utf-8"))
            assert "api_key" not in persisted
            assert persisted["unrelated"] == "preserved"
            with Session(engine) as session:
                assert credential_migration.migrate_legacy_model_settings(session) is False
            engine.dispose()
    finally:
        credential_migration.SETTINGS_PATH = original_settings_path
        credential_migration.get_ops_agent_secret_key = original_secret_provider


def scenario_production_configuration_fails_closed() -> None:
    names = (
        "OPS_AGENT_AUTH_DISABLED",
        "OPS_AGENT_ALLOWED_HOSTS",
        "OPS_AGENT_SECRET_KEY",
        "OPS_AGENT_API_TOKEN",
    )
    previous_env = {name: os.environ.get(name) for name in names}
    previous_mode = api_module.IS_PRODUCTION
    try:
        api_module.IS_PRODUCTION = True
        for name in names:
            os.environ.pop(name, None)
        try:
            api_module._validate_production_configuration()
        except RuntimeError as exc:
            assert "ALLOWED_HOSTS" in str(exc)
        else:
            raise AssertionError("Production accepted a missing allowed-host list")
        os.environ.update({
            "OPS_AGENT_ALLOWED_HOSTS": "ops.example.invalid,backend",
            "OPS_AGENT_SECRET_KEY": "s" * 32,
            "OPS_AGENT_API_TOKEN": "t" * 32,
        })
        api_module._validate_production_configuration()
        os.environ["OPS_AGENT_AUTH_DISABLED"] = "true"
        try:
            api_module._validate_production_configuration()
        except RuntimeError as exc:
            assert "cannot be disabled" in str(exc)
        else:
            raise AssertionError("Production accepted disabled API authentication")
    finally:
        api_module.IS_PRODUCTION = previous_mode
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def scenario_desktop_updater_artifacts_are_validated() -> None:
    with TemporaryDirectory(prefix="ops-agent-updater-eval-") as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        expected_suffixes = {
            "linux": "Ops Agent.AppImage",
            "macos": "Ops Agent.app.tar.gz",
            "windows": "Ops Agent-setup.exe",
        }
        for release_platform, bundle_name in expected_suffixes.items():
            bundle_root = root / f"bundle-{release_platform}"
            bundle_root.mkdir()
            bundle = bundle_root / bundle_name
            bundle.write_bytes(f"{release_platform}-bundle".encode())
            signature = bundle.with_name(f"{bundle.name}.sig")
            signature.write_text(f"{release_platform}-signature\n", encoding="utf-8")
            output = artifacts / release_platform
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "prepare_release_output.py"),
                    "--platform",
                    release_platform,
                    "--bundle-root",
                    str(bundle_root),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        manifest_path = artifacts / "latest.json"
        manifest_command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_updater_manifest.py"),
            str(artifacts),
            "--repository",
            "example/ops-agent",
            "--tag",
            "v1.2.3",
            "--version",
            "1.2.3",
            "--output",
            str(manifest_path),
        ]
        subprocess.run(manifest_command, check=True, capture_output=True, text=True)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == "1.2.3"
        assert set(manifest["platforms"]) == {
            "linux-x86_64",
            "darwin-x86_64",
            "windows-x86_64",
        }
        assert "%20" in manifest["platforms"]["linux-x86_64"]["url"]
        assert manifest["platforms"]["windows-x86_64"]["signature"] == "windows-signature"

        duplicate = artifacts / "duplicate"
        duplicate.mkdir()
        (duplicate / "bundle").write_bytes(b"duplicate")
        (duplicate / "bundle.sig").write_text("duplicate-signature", encoding="utf-8")
        (duplicate / "updater-metadata.json").write_text(
            json.dumps({
                "target": "linux-x86_64",
                "bundle": "bundle",
                "signature": "bundle.sig",
            }),
            encoding="utf-8",
        )
        duplicate_result = subprocess.run(manifest_command, capture_output=True, text=True)
        assert duplicate_result.returncode != 0
        assert "Duplicate updater target" in duplicate_result.stderr

        (duplicate / "updater-metadata.json").write_text(
            json.dumps({
                "target": "invalid-target",
                "bundle": "../bundle",
                "signature": "bundle.sig",
            }),
            encoding="utf-8",
        )
        unsafe_result = subprocess.run(manifest_command, capture_output=True, text=True)
        assert unsafe_result.returncode != 0
        assert "Invalid updater target" in unsafe_result.stderr


def main() -> int:
    scenarios = [
        ("text_stream_uses_deltas_and_final_snapshot", scenario_text_stream_uses_deltas_and_final_snapshot),
        ("event_window_gap_falls_back_to_durable_store", scenario_event_window_gap_falls_back_to_durable_store),
        ("terminal_authorization_is_runtime_scoped", scenario_terminal_authorization_is_runtime_scoped),
        ("command_scope_rechecks_asset_allowlist", scenario_command_scope_rechecks_asset_allowlist),
        ("cancel_terminalizes_runtime_and_revokes_secrets", scenario_cancel_terminalizes_runtime_and_revokes_secrets),
        ("runtime_state_machine_rejects_invalid_transitions", scenario_runtime_state_machine_rejects_invalid_transitions),
        ("local_execution_can_be_cancelled", scenario_local_execution_can_be_cancelled),
        ("interrupted_runtime_exposes_safe_recovery_action", scenario_interrupted_runtime_exposes_safe_recovery_action),
        ("command_trust_is_exact_and_context_scoped", scenario_command_trust_is_exact_and_context_scoped),
        ("legacy_global_allow_is_removed_atomically", scenario_legacy_global_allow_is_removed_atomically),
        ("audit_chain_serializes_concurrent_writers_and_detects_tampering", scenario_audit_chain_serializes_concurrent_writers_and_detects_tampering),
        ("http_limits_and_security_headers_are_enforced", scenario_http_limits_and_security_headers_are_enforced),
        ("ssh_clients_reject_unknown_hosts", scenario_ssh_clients_reject_unknown_hosts),
        ("database_backup_is_verified_before_restore", scenario_database_backup_is_verified_before_restore),
        ("plaintext_model_key_migrates_to_encrypted_storage", scenario_plaintext_model_key_migrates_to_encrypted_storage),
        ("production_configuration_fails_closed", scenario_production_configuration_fails_closed),
        ("desktop_updater_artifacts_are_validated", scenario_desktop_updater_artifacts_are_validated),
    ]
    results: list[dict[str, str]] = []
    for name, scenario in scenarios:
        try:
            scenario()
        except Exception as exc:
            results.append({"name": name, "status": "failed", "error": str(exc)})
        else:
            results.append({"name": name, "status": "passed"})
    report = {
        "suite": "runtime-events",
        "passed": sum(item["status"] == "passed" for item in results),
        "total": len(results),
        "scenarios": results,
    }
    report["status"] = "passed" if report["passed"] == report["total"] else "failed"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
