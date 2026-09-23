#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import ast
import importlib.util
import json
import os
import sqlite3
import socket
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
from app.db.repositories.runtime import RuntimeStore
from app.services.instance_service import get_instance_info
from app.core.loop.runtime_models import RuntimeTerminalAuthorization
from app.core.loop.state_machine import RuntimeStateTransitionError, transition_runtime_state
from app.core.tool.execute_command import ExecuteCommandHandler
from app.core.connectors.execution import ExecutionContext
from app.core.connectors.local_pty import LocalPtyConnector
from app.core.connectors.session_manager import TerminalSessionManager
from app.core.connectors.ssh_host_keys import configure_strict_ssh_client, strict_netmiko_options
from app.core.connectors.tcp_proxy import TCPProxyConfig, open_proxy_socket
from app.core.approval import ApprovalChecker, ApprovalContext, ApprovalPermissions, ApprovalPolicy, TrustedCommandRule
from app.db.models import AuditLog, ModelConfigRecord
import app.db.repositories.audit as audit_repository
import app.db.migrations as database_migrations
import app.api as api_module
from app.api.middleware.security import RequestLimitMiddleware, SecurityHeadersMiddleware
from app.services.approval_service import ApprovalService
import app.services.credential_migration_service as credential_migration
from app.db.repositories.runtime import interruption_recovery
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
    manager = LoopRuntimeManager(tools_factory=lambda _: [], runtime_store=RuntimeStore(instance_id=get_instance_info().instance_id))
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
    manager = LoopRuntimeManager(tools_factory=lambda _: [], runtime_store=RuntimeStore(instance_id=get_instance_info().instance_id))
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

    manager = LoopRuntimeManager(tools_factory=lambda _: [], runtime_store=RuntimeStore(instance_id=get_instance_info().instance_id))
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
            import paramiko
            assert isinstance(client.policy, paramiko.RejectPolicy)
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


def scenario_ssh_host_key_confirmation_roundtrip() -> None:
    import paramiko
    from unittest.mock import patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import terminal, assets
    from app.core.connectors.server import ServerConnector
    from app.core.connectors.ssh_host_keys import UnknownSSHHostKey, trust_host_key
    from app.services import ssh_host_key_service as trust_service
    from app.services import asset_connection_service
    from app.services.terminal_service import TerminalService

    server_key = [paramiko.RSAKey.generate(2048)]
    auth_calls: list[str] = []
    transports: list[paramiko.Transport] = []
    stopped = threading.Event()

    class SSHServer(paramiko.ServerInterface):
        def check_auth_password(self, username, password):
            auth_calls.append(username)
            return paramiko.AUTH_SUCCESSFUL

        def check_channel_request(self, kind, chanid):
            return paramiko.OPEN_SUCCEEDED

        def check_channel_pty_request(self, *args):
            return True

        def check_channel_shell_request(self, channel):
            return True

    listener = socket.socket()
    for port in range(55000, 55100):
        try:
            listener.bind(("0.0.0.0", port))
            break
        except OSError:
            continue
    else:
        listener.close()
        raise AssertionError("No available test port")
    listener.listen()
    listener.settimeout(0.2)

    def serve():
        while not stopped.is_set():
            try:
                sock, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            transport = paramiko.Transport(sock)
            transports.append(transport)
            transport.add_server_key(server_key[0])
            try:
                transport.start_server(server=SSHServer())
            except (EOFError, OSError, paramiko.SSHException):
                # Host-key rejection can reset the socket before authentication.
                transport.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    asset = SimpleNamespace(id=991, asset_type="linux", host="127.0.0.1", port=port, username="test")
    service = TerminalService(lambda _: ServerConnector(asset.host, port, "test", password="test-only"))
    app = FastAPI()
    app.include_router(terminal.router)
    app.include_router(assets.router)
    app.dependency_overrides[terminal.get_terminal_service] = lambda: service
    app.dependency_overrides[terminal.get_session] = lambda: None
    try:
        with TemporaryDirectory(prefix="ops-agent-host-trust-") as tmp:
            path = Path(tmp) / "known_hosts"
            path.write_text("# existing operator entries\n")
            with patch.dict(os.environ, {"OPS_AGENT_KNOWN_HOSTS_FILE": str(path)}), patch.object(terminal, "_get_terminal_asset", return_value=asset), TestClient(app) as client:
                result = client.post("/api/terminal/sessions", json={"asset_id": asset.id}).json()
                challenge = result["host_key"]
                assert result["terminal_id"] is None and challenge["fingerprint"].startswith("SHA256:")
                assert challenge["hostname"] == f"[127.0.0.1]:{port}"
                assert not auth_calls, "Unknown hosts must fail before sending credentials"
                assert path.read_text() == "# existing operator entries\n", "No confirmation must mean no persistence"
                with patch.object(asset_connection_service, "connector_factory", side_effect=lambda *args, **kwargs: ServerConnector(asset.host, port, "test", password="test-only")):
                    probe = client.post("/api/assets/connection-test", json={"asset": {
                        "name": "New host", "asset_type": "linux", "host": asset.host,
                        "port": port, "username": "test", "auth_type": "password",
                    }}).json()
                assert probe["success"] is False and probe["host_key"]["fingerprint"] == challenge["fingerprint"]
                assert not auth_calls and path.read_text() == "# existing operator entries\n"
                assert client.post("/api/terminal/host-key/confirm", json={"asset_id": 992, "token": challenge["token"]}).status_code == 409
                assert client.post("/api/terminal/host-key/confirm", json={"asset_id": asset.id, "token": "forged"}).status_code == 409
                assert client.post("/api/terminal/host-key/confirm", json={"asset_id": asset.id, "token": challenge["token"]}).status_code == 204
                assert client.post("/api/terminal/host-key/confirm", json={"asset_id": asset.id, "token": challenge["token"]}).status_code == 409
                saved = path.read_text()
                trust_host_key(challenge["hostname"], server_key[0])
                assert path.read_text() == saved, "Trust writes must be idempotent"
                result = client.post("/api/terminal/sessions", json={"asset_id": asset.id}).json()
                assert result["terminal_id"] and result["host_key"] is None and auth_calls == ["test"]
                service.close_session(result["terminal_id"])
                server_key[0] = paramiko.RSAKey.generate(2048)
                result = client.post("/api/terminal/sessions", json={"asset_id": asset.id}).json()
                assert result["terminal_id"] is None and result["host_key"] is None
                assert len(auth_calls) == 1, "Changed host must fail before authentication"
                try:
                    trust_host_key(challenge["hostname"], server_key[0])
                except ValueError:
                    pass
                else:
                    raise AssertionError("Changed key was accepted")
                assert path.read_text() == saved
                # Proxy wrappers preserve the challenge; expired tokens cannot write.
                wrapped = RuntimeError("Proxy connection failed")
                wrapped.__cause__ = UnknownSSHHostKey("new-host", server_key[0])
                pending = trust_service.host_key_challenge(wrapped, asset.id)
                assert pending is not None
                with patch.object(trust_service.time, "monotonic", return_value=time.monotonic() + 601):
                    assert client.post("/api/terminal/host-key/confirm", json={"asset_id": asset.id, "token": pending["token"]}).status_code == 409
                assert path.read_text() == saved
    finally:
        stopped.set()
        listener.close()
        for transport in transports:
            transport.close()
        worker.join(timeout=2)
        trust_service._pending.clear()


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
                assert records[0].is_default is False
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


def scenario_tcp_proxy_handshakes_are_supported() -> None:
    class FakeSocket:
        def __init__(self, responses: list[bytes]) -> None:
            self.responses = deque(responses)
            self.sent: list[bytes] = []
            self.closed = False

        def sendall(self, data: bytes) -> None:
            self.sent.append(data)

        def recv(self, size: int) -> bytes:
            _ = size
            return self.responses.popleft()

        def close(self) -> None:
            self.closed = True

    original_create_connection = socket.create_connection
    try:
        http_socket = FakeSocket([b"HTTP/1.1 200 Connection Established\r\n\r\n"])
        socket.create_connection = lambda *args, **kwargs: http_socket  # type: ignore[method-assign]
        result = open_proxy_socket(TCPProxyConfig("http_connect", "proxy", 8080, "u", "p"), "target", 22)
        assert result is http_socket
        assert b"CONNECT target:22 HTTP/1.1" in http_socket.sent[0]
        assert b"Proxy-Authorization: Basic dTpw" in http_socket.sent[0]

        socks_socket = FakeSocket([b"\x05\x00", b"\x05\x00\x00\x01", b"\x7f\x00\x00\x01\x00\x16"])
        socket.create_connection = lambda *args, **kwargs: socks_socket  # type: ignore[method-assign]
        assert open_proxy_socket(TCPProxyConfig("socks5", "proxy", 1080), "target", 22) is socks_socket
        assert socks_socket.sent[0] == b"\x05\x01\x00"
        assert socks_socket.sent[1].startswith(b"\x05\x01\x00\x03")
    finally:
        socket.create_connection = original_create_connection



def _module_imports(source: str, package: str) -> set[str]:
    dependencies: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            dependencies.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = "." * node.level + (node.module or "")
            base = importlib.util.resolve_name(target, package) if node.level else target
            dependencies.add(base)
            dependencies.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in {"__import__", "import_module"} and isinstance(node.args[0].value, str):
                target = node.args[0].value
                dependencies.add(importlib.util.resolve_name(target, package) if target.startswith(".") else target)
    return dependencies


def scenario_module_dependency_boundaries() -> None:
    assert "app.services.asset_service" in _module_imports(
        "def lazy():\n from ...services import asset_service", "app.core.tool"
    )
    assert "app.db.models" in _module_imports('__import__("app.db.models")', "app.core")
    forbidden = {
        "core": ("app.api", "app.composition", "app.services", "app.db", "sqlmodel", "sqlalchemy", "fastapi", "starlette"),
        "services": ("app.api", "app.composition", "fastapi", "starlette"),
        "db": ("app.api", "app.composition", "app.services", "fastapi", "starlette"),
        "shared": ("app.api", "app.composition", "app.services", "app.db", "app.core"),
        "utils": ("app.api", "app.composition", "app.services", "app.db", "app.core"),
    }
    violations: list[str] = []
    root = REPO_ROOT / "src" / "app"
    for layer, denied in forbidden.items():
        for path in sorted((root / layer).rglob("*.py")):
            package = ".".join(path.relative_to(REPO_ROOT / "src").parts[:-1])
            for dependency in sorted(_module_imports(path.read_text(encoding="utf-8"), package)):
                if any(dependency == prefix or dependency.startswith(prefix + ".") for prefix in denied):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {dependency}")
    for layer, denied in {
        "prompts": ("app.core.loop", "app.core.tool", "app.core.connectors", "app.core.llm"),
        "connectors": ("app.core.loop", "app.core.tool", "app.core.llm", "app.core.prompts"),
        "llm": ("app.core.loop", "app.core.prompts", "app.core.connectors"),
    }.items():
        for path in sorted((root / "core" / layer).rglob("*.py")):
            package = ".".join(path.relative_to(REPO_ROOT / "src").parts[:-1])
            for dependency in sorted(_module_imports(path.read_text(encoding="utf-8"), package)):
                if any(dependency == prefix or dependency.startswith(prefix + ".") for prefix in denied):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {dependency}")
    assert not violations, "Module boundary violations:\n" + "\n".join(violations)


def scenario_injected_command_policy_preserves_approval_and_audit() -> None:
    from unittest.mock import Mock

    terminal = Mock()
    policy = Mock()
    handler = ExecuteCommandHandler(terminal, policy=policy)
    policy.check_command.return_value = ("allow", "trusted")
    assert handler.needs_approval({"authorization_id": "auth", "command": "printf ok"})[0] == "ask"
    policy.check_command.return_value = ("deny", "blocked")
    assert handler.needs_approval({"authorization_id": "auth", "command": "printf ok"}) == ("deny", "blocked")
    terminal.resolve_terminal_authorization.return_value = SimpleNamespace(
        authorization_id="auth", asset_id=1, asset_name="local", terminal_id="term",
        asset_type="linux", shell_type="bash", execution_profile="posix-shell", device_vendor=None,
    )
    state = SimpleNamespace(
        context=SimpleNamespace(runtime_id="test", conversation_id="test", asset_id=1,
            conversation_primary_asset_id=1, conversation_scope_mode="single", allowed_asset_ids=[1]),
        get_step=lambda _: SimpleNamespace(step_id="step", working_directory=None),
    )
    policy.record_submission.side_effect = RuntimeError("audit unavailable")
    execution = handler.execute(state=state, step_id="step", args={"authorization_id": "auth", "command": "printf ok"})
    try:
        next(execution)
    except StopIteration as result:
        assert result.value == (False, "Command execution exception: audit unavailable")
    else:
        raise AssertionError("Expected the command to stop before execution")
    terminal.get_session.return_value.start_execution.assert_not_called()
    terminal.release_terminal_slot.assert_called_once_with("test", "term")


def scenario_terminal_channel_disconnect_detaches_session() -> None:
    from unittest.mock import Mock
    from app.services.terminal_service import TerminalService, TerminalSessionRuntime
    from app.services.terminal_channel import TerminalChannelClosed
    from app.api.terminal_channel import WebSocketTerminalChannel
    from starlette.websockets import WebSocketDisconnect

    class Channel:
        accepted = False
        async def accept(self, **kwargs):
            self.accepted = True
        async def close(self, **kwargs):
            pass
        async def receive_json(self):
            raise TerminalChannelClosed()
        async def send_json(self, data):
            pass

    async def check():
        service = TerminalService(connector_factory=Mock())
        session = Mock()
        session.read.return_value = ""
        runtime = TerminalSessionRuntime(session_manager=session)
        service._sessions["terminal"] = runtime
        channel = Channel()
        await service.stream_session("terminal", channel)
        assert channel.accepted
        assert runtime.state == "detached"
        assert not runtime.connection_ids
        assert runtime.last_detached_at is not None

        class BufferedDisconnect(Channel):
            async def send_json(self, data):
                raise TerminalChannelClosed()
        service.read_buffered_output = lambda _: "buffered output"
        await service.stream_session("terminal", BufferedDisconnect())
        assert runtime.state == "detached"
        assert not runtime.connection_ids

        class DisconnectedSocket:
            async def receive_json(self):
                raise WebSocketDisconnect()
        adapter = WebSocketTerminalChannel(DisconnectedSocket())
        try:
            await adapter.receive_json()
        except TerminalChannelClosed:
            pass
        else:
            raise AssertionError("Transport exception was not adapted")

    asyncio.run(check())



def scenario_mcp_callbacks_keep_tool_identity_and_policy() -> None:
    from unittest.mock import Mock
    from app.services.mcp_service import McpService, MCPCallResult

    pairs = [
        (SimpleNamespace(id=f"server-{i}"), SimpleNamespace(exposed_name=f"tool-{i}",
            original_name=f"original-{i}", description="", input_schema={}, approval_policy=policy))
        for i, policy in enumerate(("ask", "deny"))
    ]
    store = Mock()
    store.list_injectable_tools.return_value = pairs
    service = McpService(store=store)
    service.call_tool = Mock(side_effect=lambda server, tool, args: MCPCallResult(
        ok=True, text_output=f"{server.id}/{tool.original_name}/{args['value']}"))
    try:
        handlers = service.build_tool_handlers()
        for i, handler in enumerate(handlers):
            assert handler.definition.name == f"tool-{i}"
            assert handler.needs_approval({})[0] == pairs[i][1].approval_policy
            # Exercise only the injected callback; the runtime owns approval gating.
            execution = handler.execute(state=None, step_id="test", args={"value": i})
            try:
                next(execution)
            except StopIteration as result:
                assert result.value == (True, f"server-{i}/original-{i}/{i}")
            else:
                raise AssertionError("Expected the callback result")
        assert service.call_tool.call_count == 2
    finally:
        service.close()


def scenario_composition_shares_runtime_services() -> None:
    from app.composition import get_console_app_service, get_terminal_service, get_scheduler_service
    from app.api.console import get_console_app_service as console_route_service
    from app.api.terminal import get_terminal_service as terminal_route_service
    scheduler = get_scheduler_service()
    assert scheduler._console_service is console_route_service() is get_console_app_service()
    assert scheduler._terminal_service is terminal_route_service() is get_terminal_service()


def scenario_jumpserver_connection_wait_budget() -> None:
    from unittest.mock import patch
    from app.services.jumpserver_ssh_client import JumpServerSSHClient
    from app.services.jumpserver_client import JumpServerError
    gateway = JumpServerSSHClient(gateway_url="ssh://example.invalid", username="test", private_key="unused")
    class Channel:
        closed = False
        def recv_ready(self):
            return clock[0] >= 35
        def recv(self, size):
            return b"Connecting to test@device"
    def sleep(seconds):
        clock[0] += seconds
    clock = [0.0]
    with patch("app.services.jumpserver_ssh_client.time.monotonic", side_effect=lambda: clock[0]), patch("app.services.jumpserver_ssh_client.time.sleep", side_effect=sleep):
        assert "Connecting to" in gateway._read_until(Channel(), ("Connecting to",), timeout=gateway.asset_connect_timeout)
        clock[0] = 0.0
        try:
            gateway._read_until(Channel(), ("Opt>",))
        except JumpServerError as error:
            assert "20 秒" in str(error) and "等待菜单" in str(error)
        else:
            raise AssertionError("Menu wait did not time out")
        clock[0] = 0.0
        try:
            gateway._read_until(Channel(), ("Connecting to",), timeout=30)
        except JumpServerError as error:
            assert "30 秒" in str(error) and "连接目标设备" in str(error)
        else:
            raise AssertionError("Configured wait did not time out")
        channel = Channel()
        channel.closed = True
        clock[0] = 0.0
        try:
            gateway._read_until(channel, ("Opt>",))
        except JumpServerError as error:
            assert "已关闭" in str(error)
        else:
            raise AssertionError("Closed channel accepted")


def scenario_background_operations_and_topology_retry() -> None:
    from unittest.mock import MagicMock, patch
    from sqlmodel import SQLModel
    from app.db.models import Asset, JumpServerInstance, JumpServerAssetBinding
    from app.services.operations_service import OperationsService
    from app.services.network_topology_service import NetworkTopologyService
    from app.services.jumpserver_service import JumpServerService
    from app.services.operation_progress import OperationProgress
    db = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(db)
    with TemporaryDirectory() as directory, Session(db) as session:
        instance = JumpServerInstance(name="fixture", auth_mode="ssh_gateway", base_url="ssh://example.invalid", org_id="", access_key_id="test", encrypted_access_key_secret="unused", access_key_secret_encryption_version="test")
        session.add(instance); session.flush()
        ids = []
        for index, org in enumerate(("A", "A", "B")):
            asset = Asset(name=f"node-{index}", asset_type="cisco", host=f"192.0.2.{index+1}", username="test", auth_type="jumpserver")
            session.add(asset); session.flush()
            ids.append(asset.id)
            session.add(JumpServerAssetBinding(instance_id=instance.id, asset_id=asset.id, external_asset_id=str(index), external_name=asset.name, org_name=org))
        session.commit()
        topology = NetworkTopologyService()
        def collect(asset, progress=None):
            if asset.id == ids[1]:
                raise ValueError("offline")
            return {"asset": asset, "facts": {"vendor": "cisco", "records": [{"hostname": asset.name}]}, "interfaces": {"records": [{"name": "Gi1"}]}, "neighbors": {"records": []}}
        updates = []
        progress = OperationProgress(lambda: False, lambda **value: updates.append(value))
        with patch.object(topology, "_collect_asset", side_effect=collect):
            first = topology.collect(session, name="A", asset_ids=ids[:2], progress=progress)
        assert first["status"] == "partial" and len(first["nodes"]) == 2
        def repaired(asset, progress=None):
            return {"asset": asset, "facts": {"records": [{"hostname": asset.name}]}, "interfaces": {"records": [{"name": "Gi1"}]}, "neighbors": {"records": []}}
        with patch.object(topology, "_collect_asset", side_effect=repaired) as collector:
            second = topology.collect(session, name="retry", asset_ids=ids[:2], previous_snapshot_id=first["id"], progress=progress)
        assert collector.call_count == 1 and collector.call_args.args[0].id == ids[1]
        assert second["status"] == "completed" and len(second["nodes"]) == 2
        assert any(value.get("completed") == 2 for value in updates)
        cancelled = OperationProgress(lambda: True, lambda **_: None)
        with patch.object(topology, "_collect_asset") as collector:
            stopped = topology.collect(session, name="cancel", asset_ids=ids[:2], progress=cancelled)
        collector.assert_not_called()
        assert len(stopped["errors"]) == 2

        service = OperationsService(Path(directory))
        payload = {"instanceId": instance.id, "organization": "A", "prompt": "inspect"}
        inspector = MagicMock()
        inspector.inspect_asset.side_effect = lambda asset_id, *_: {"assetId": asset_id, "status": "completed" if asset_id == ids[0] else "failed", "message": "result"}
        service.bind(inspect_asset=inspector.inspect_asset, runtime_lookup=lambda _: None)
        with patch("app.services.operations_service.engine", db):
            operation = service.start("inspection", payload, inline=True)
            assert operation["status"] == "partial" and operation["total"] == 2
            assert {item["assetId"] for item in operation["items"]} == set(ids[:2])
            inspector.inspect_asset.reset_mock()
            inspector.inspect_asset.side_effect = lambda asset_id, *_: {"assetId": asset_id, "status": "completed", "message": "repaired"}
            with patch.object(service._executor, "submit"):
                retried = service.retry(operation["id"])
                service._run(retried["id"])
            assert inspector.inspect_asset.call_count == 1
            assert inspector.inspect_asset.call_args.args[0] == ids[1]
            assert service.get(retried["id"])["status"] == "completed"
            assert len(service.get(retried["id"])["items"]) == 2
            with patch.object(service._executor, "submit"):
                queued = service.start("inspection", payload)
                try:
                    service.start("inspection", payload)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Duplicate background job allowed")
                service.cancel(queued["id"])
                service._run(queued["id"])
                assert service.get(queued["id"])["status"] == "cancelled"
                before_discovery = service.retry(queued["id"])
                service._run(before_discovery["id"])
                assert service.get(before_discovery["id"])["total"] == 2
                inspector.inspect_asset.side_effect = lambda asset_id, *_: {"assetId": asset_id, "status": "waiting_approval" if asset_id == ids[0] else "failed", "message": "pending"}
                pending = service.start("inspection", payload, inline=True)
                for _ in range(2):
                    pending = service.retry(pending["id"])
                    service._run(pending["id"])
                    pending = service.get(pending["id"])
                    assert pending["status"] == "partial"
                # Resolve the retained human approval before starting a new batch.
                for saved in service._jobs.values():
                    for item in saved["items"]:
                        if item["status"] == "waiting_approval":
                            item["status"] = "completed"
                interrupted = service.start("inspection", payload)
            # Simulate process restart by reopening persisted jobs before the old
            # service can perform shutdown cancellation.
            recovered = OperationsService(Path(directory))
            assert recovered.get(interrupted["id"])["status"] == "interrupted"
            assert recovered.get(retried["id"])["status"] == "completed"
            recovered.close()
        service.close()
    db.dispose()


def scenario_organization_inspection_keeps_approvals() -> None:
    from unittest.mock import MagicMock, patch
    from sqlmodel import SQLModel
    from app.services.conversation_service import ConversationService
    from app.services.scheduler_service import SchedulerService
    from app.services.operation_progress import OperationProgress
    db = create_engine("sqlite://")
    SQLModel.metadata.create_all(db)
    with TemporaryDirectory() as directory, patch("app.services.scheduler_service.engine", db), patch("app.services.scheduler_service.get_alert_service", return_value=MagicMock()):
        conversations = ConversationService(Path(directory))
        console = MagicMock()
        console.resolve_model_config.return_value.model_name = "test"
        state = SimpleNamespace(phase="waiting_terminal_approval", summary="", error_message="")
        console.runtime_manager.get_runtime.return_value = SimpleNamespace(state=state)
        console.stream_run.side_effect = lambda **_: iter([{"runtimeId": "runtime-test", "kind": "task_state"}])
        scheduler = SchedulerService(console_service=console, terminal_service=MagicMock(), conversation_factory=lambda: conversations)
        result = scheduler.inspect_asset(7, "inspect", "device")
        assert result["status"] == "waiting_approval" and result["conversationId"]
        assert conversations.get_conversation(result["conversationId"]).allowed_asset_ids == [7]
        console.runtime_manager.resume.assert_not_called()
        console.runtime_manager.decide_terminal_request.assert_not_called()
        state.phase, state.summary = "completed", "[ALERT: Port] down"
        assert scheduler.inspect_asset(7, "inspect", "device")["status"] == "warning"
        result = scheduler.inspect_asset(7, "inspect", "device", progress=OperationProgress(lambda: True, lambda **_: None))
        assert result["status"] == "cancelled"
        console.runtime_manager.cancel.assert_called_once()
    db.dispose()


def scenario_empty_conversation_reuse() -> None:
    from concurrent.futures import ThreadPoolExecutor
    from app.services.conversation_service import ConversationService
    with TemporaryDirectory() as directory:
        service = ConversationService(Path(directory))
        with ThreadPoolExecutor(max_workers=4) as pool:
            drafts = list(pool.map(lambda _: service.create_conversation("model"), range(8)))
        assert len({item.id for item in drafts}) == 1
        draft = drafts[0]
        assert service.create_conversation("other-model").id == draft.id
        bound = service.create_conversation("model", asset_id=7)
        assert bound.id != draft.id
        assert service.create_conversation("model", asset_id=7).id == bound.id
        assert service.create_conversation("model", asset_id=8).id != bound.id
        assert service.create_conversation("model", asset_id=7, scope_mode="multi", allowed_asset_ids=[7, 8]).id != bound.id
        service.append_events(draft.id, [{"id": "user-1", "kind": "user", "text": "work"}], async_title_generation=False)
        next_draft = service.create_conversation("model")
        assert next_draft.id != draft.id
        reserved = service.create_conversation("model", can_reuse=lambda _: False)
        assert reserved.id != next_draft.id
        assert service.get_conversation(draft.id).events[0]["text"] == "work"


def scenario_jumpserver_organization_sync() -> None:
    from unittest.mock import MagicMock, patch
    from sqlmodel import SQLModel
    from app.db.models import Asset, JumpServerInstance, JumpServerAssetBinding
    from app.services.jumpserver_service import JumpServerService
    from app.services.jumpserver_ssh_client import JumpServerSSHClient
    from app.services.jumpserver_client import JumpServerError
    from app.services.network_topology_service import NetworkTopologyService
    gateway = JumpServerSSHClient(gateway_url="ssh://example.invalid", username="test", private_key="unused")
    page_a = "1 | core | 192.0.2.1 | Cisco | 组织 A | comment\n页码：1，每页行数：1，总页数：2，总数量：2\n[Host]>"
    page_b = "2 | core | 192.0.2.1 | Cisco | 组织 B | comment\n页码：2，每页行数：1，总页数：2，总数量：2\n[Host]>"
    with patch.object(gateway, "_connect", return_value=MagicMock()), patch.object(gateway, "_read_until", side_effect=["Opt>", page_a, page_b]):
        remote = gateway.list_all_assets()
    assert len(remote) == 2 and remote[0]["id"] != remote[1]["id"]
    english = page_a.replace("页码：1，每页行数：1，总页数：2，总数量：2", "Page: 1, Count: 1, Total Page: 1, Total Count: 1")
    with patch.object(gateway, "_connect", return_value=MagicMock()), patch.object(gateway, "_read_until", side_effect=["Opt>", english]):
        assert len(gateway.list_all_assets()) == 1
    with patch.object(gateway, "_connect", return_value=MagicMock()), patch.object(gateway, "_read_until", side_effect=["Opt>", "Page: 0, Count: 40, Total Page: 0, Total Count: 0\n[Host]>"]):
        assert gateway.list_all_assets() == []
    assert gateway._find_asset_row(page_a + "\n" + page_b, asset_name="core", address="192.0.2.1") is None
    assert gateway._find_asset_row(page_a + "\n" + page_b, asset_name="core", address="192.0.2.1", org_name="组织 B") == "2"
    for pages in ([page_a, page_a], [page_a, page_b.replace("总数量：2", "总数量：3")], ["[Host]>"]):
        with patch.object(gateway, "_connect", return_value=MagicMock()), patch.object(gateway, "_read_until", side_effect=["Opt>", *pages]):
            try:
                gateway.list_all_assets()
            except JumpServerError:
                pass
            else:
                raise AssertionError("Incomplete SSH inventory accepted")
    db = create_engine("sqlite://")
    SQLModel.metadata.create_all(db)
    service = JumpServerService()
    with Session(db) as session:
        instance = JumpServerInstance(name="fixture", auth_mode="ssh_gateway", base_url="ssh://example.invalid", org_id="", access_key_id="test", access_key_secret_encryption_version="test", encrypted_access_key_secret="unused")
        legacy = Asset(name="core", asset_type="cisco", host="192.0.2.1", username="test", auth_type="jumpserver")
        session.add(instance); session.add(legacy); session.flush()
        assert instance.id is not None and legacy.id is not None
        instance_id, legacy_id = instance.id, legacy.id
        binding = JumpServerAssetBinding(instance_id=instance_id, asset_id=legacy_id, external_asset_id="legacy", external_name="core", address="192.0.2.1")
        session.add(binding); session.commit()
        fake = MagicMock()
        fake.list_all_assets.return_value = remote
        with patch.object(service, "gateway_client", return_value=fake), patch.object(service, "client", side_effect=AssertionError("SSH sync must never call the HTTP client")):
            result = service.sync(session, instance_id)
            assert result["created"] == 1 and result["updated"] == 1
            again = service.sync(session, instance_id)
            assert again["created"] == 0 and again["updated"] == 2
        groups = service.list_organizations(session, instance_id)
        assert len(groups) == 2 and groups[0]["networkAssetIds"] == [legacy_id]
        imported = service.list_assets(session, instance_id)
        assert all(item["active"] for item in imported)
        assert len({session.get(Asset, item["assetId"]).group_id for item in imported}) == 2
        topology = NetworkTopologyService()
        with patch("app.services.network_topology_service.get_jumpserver_service", return_value=service), patch.object(topology, "_collect_asset", side_effect=ValueError("unreachable")):
            snapshot = topology.collect_organization(session, instance_id=instance_id, organization="组织 A", name="", max_workers=1)
        assert snapshot["requestedAssetIds"] == [legacy_id]
        assert snapshot["status"] == "failed" and len(snapshot["nodes"]) == 1 and len(snapshot["errors"]) == 1
        assert not snapshot["links"]
        assert snapshot["instanceId"] == instance_id and snapshot["organization"] == "组织 A"
        from app.db.models import NetworkTopologySnapshot
        # Unscoped legacy data and a same-named organization on another instance
        # must never appear in this organization's snapshot history.
        session.add(NetworkTopologySnapshot(name="legacy mixed", requested_asset_ids_json=json.dumps([item["assetId"] for item in imported])))
        session.add(NetworkTopologySnapshot(name="other instance", instance_id=instance_id + 1, organization="组织 A"))
        session.commit()
        with patch("app.services.network_topology_service.get_jumpserver_service", return_value=service), patch.object(topology, "_collect_asset", side_effect=ValueError("unreachable")) as collector:
            second = topology.collect_organization(session, instance_id=instance_id, organization="组织 B", name="", max_workers=1)
            collector.reset_mock()
            try:
                topology.collect(session, name="mixed", asset_ids=[item["assetId"] for item in imported])
            except ValueError as error:
                assert "单个组织" in str(error)
            else:
                raise AssertionError("Cross-organization topology accepted")
            collector.assert_not_called()
        assert [item["id"] for item in topology.list(session, instance_id=instance_id, organization="组织 A")] == [snapshot["id"]]
        assert [item["id"] for item in topology.list(session, instance_id=instance_id, organization="组织 B")] == [second["id"]]
        assert topology.list(session, instance_id=instance_id, organization="unknown") == []
    db.dispose()


def scenario_context_usage_is_not_cumulative() -> None:
    from unittest.mock import MagicMock
    from app.core.loop.runtime_manager import LoopRuntimeManager
    from app.services.console_app_service import ConsoleAppService
    manager = LoopRuntimeManager(tools_factory=lambda _: [], runtime_store=MagicMock(), usage_callback=MagicMock())
    context = LoopContext(runtime_id="context-usage-eval", conversation_id="context-usage-eval", asset_id=0, asset_type="local_terminal", terminal_id=None, asset_summary="eval", shell_type="bash", os_type="linux", user_prompt="test", model_config=ModelConfig(model_name="gpt-5-test", provider=ModelProvider.OPENAI_COMPATIBLE, base_url="http://invalid", api_key=SecretStr("unused")))
    state = manager.create_runtime(conversation_id=context.conversation_id, asset_id=0, terminal_id=None, context=context)
    state.latest_usage = {"requestInputTokens": 6200, "totalTokens": 212390, "measurement": "reported"}
    runtime = manager.get_runtime(context.runtime_id)
    event = manager._build_usage_event(runtime)
    assert event is not None and event["contextPercent"] == 5
    assert event["tokenUsage"]["totalTokens"] == 212390
    assert "requestInputTokens" not in event["tokenUsage"]
    assert ConsoleAppService._context_percent_for_status_event(MagicMock(), context_percent=0, token_usage={"totalTokens": 212390}, model_config=context.model_config) == 0
    # Refresh must use the latest agent call, including its cached input.
    import importlib
    from unittest.mock import patch
    from app.core.llm.types import LLMTokenUsage
    api = importlib.import_module("app.api.conversations")
    db = MagicMock()
    db.__enter__.return_value.exec.return_value.first.return_value = SimpleNamespace(
        model_name="gpt-5-test", input_tokens=1200, cache_read_input_tokens=4000, cache_creation_input_tokens=1000,
    )
    with TemporaryDirectory() as tmp, patch.object(api, "Session", return_value=db), patch.object(api, "sum_conversation_usage", return_value=LLMTokenUsage(input_tokens=200000)), patch.object(api, "get_conversation_service", return_value=SimpleNamespace(base_dir=Path(tmp), get_conversation=lambda _: SimpleNamespace(events=[]))), patch.object(api.ModelService, "load_settings", return_value=context.model_config):
        refreshed = api.get_conversation_context("eval")
    assert refreshed.context_measurement == "reported" and refreshed.request_input_tokens == 6200
    assert refreshed.context_percent == 5 and refreshed.cache_read_tokens == 4000
    assert refreshed.cache_write_tokens == 1000 and refreshed.token_usage.total_tokens == 200000


def main() -> int:
    scenarios = [
        ("background_operations_and_topology_retry", scenario_background_operations_and_topology_retry),
        ("organization_inspection_keeps_approvals", scenario_organization_inspection_keeps_approvals),
        ("empty_conversation_reuse", scenario_empty_conversation_reuse),
        ("jumpserver_organization_sync", scenario_jumpserver_organization_sync),
        ("context_usage_is_not_cumulative", scenario_context_usage_is_not_cumulative),
        ("jumpserver_connection_wait_budget", scenario_jumpserver_connection_wait_budget),
        ("mcp_callbacks_keep_tool_identity_and_policy", scenario_mcp_callbacks_keep_tool_identity_and_policy),
        ("composition_shares_runtime_services", scenario_composition_shares_runtime_services),
        ("module_dependency_boundaries", scenario_module_dependency_boundaries),
        ("injected_command_policy_preserves_approval_and_audit", scenario_injected_command_policy_preserves_approval_and_audit),
        ("terminal_channel_disconnect_detaches_session", scenario_terminal_channel_disconnect_detaches_session),
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
        ("ssh_host_key_confirmation_roundtrip", scenario_ssh_host_key_confirmation_roundtrip),
        ("database_backup_is_verified_before_restore", scenario_database_backup_is_verified_before_restore),
        ("plaintext_model_key_migrates_to_encrypted_storage", scenario_plaintext_model_key_migrates_to_encrypted_storage),
        ("production_configuration_fails_closed", scenario_production_configuration_fails_closed),
        ("desktop_updater_artifacts_are_validated", scenario_desktop_updater_artifacts_are_validated),
        ("tcp_proxy_handshakes_are_supported", scenario_tcp_proxy_handshakes_are_supported),
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
