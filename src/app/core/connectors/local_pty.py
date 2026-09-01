import os
import platform
import select
import signal
import subprocess
import threading
from pathlib import Path

from app.core.connectors.execution import ExecutionContext, ExecutionEvent, ExecutionResult


def _resolve_working_directory(context: ExecutionContext | None) -> str | None:
    if context is None or not context.working_directory:
        return None
    return os.path.expandvars(os.path.expanduser(context.working_directory))


def _resolve_timeout(context: ExecutionContext | None) -> float | None:
    if context is None or context.timeout_seconds is None or context.timeout_seconds <= 0:
        return None
    return context.timeout_seconds


def _timeout_result(command: str, exc: subprocess.TimeoutExpired) -> ExecutionResult:
    stdout = exc.stdout.decode(errors="ignore") if isinstance(exc.stdout, bytes) else exc.stdout or ""
    stderr = exc.stderr.decode(errors="ignore") if isinstance(exc.stderr, bytes) else exc.stderr or ""
    output = f"{stdout}{stderr}".strip()
    if output:
        output = f"{output}\nCommand timed out after {exc.timeout:g} seconds: {command}"
    else:
        output = f"Command timed out after {exc.timeout:g} seconds: {command}"
    return ExecutionResult(
        execution_id="local-sync",
        output=output,
        completed=True,
        success=False,
        needs_attention=True,
        exit_code=None,
        completion_reason="timeout",
    )


def _resolve_windows_shell() -> str:
    pwsh_path = os.environ.get("OPS_AGENT_PWSH_PATH")
    if pwsh_path:
        return pwsh_path

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidate_paths = [
        os.path.join(local_app_data, "Microsoft", "WindowsApps", "pwsh.exe") if local_app_data else "",
        r"C:\Program Files\PowerShell\7\pwsh.exe",
        r"C:\Program Files (x86)\PowerShell\7\pwsh.exe",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    ]

    for candidate in candidate_paths:
        if candidate and os.path.exists(candidate):
            return candidate

    return os.environ.get("COMSPEC") or "cmd.exe"


class LocalPtyConnector:
    def __init__(self, *, cols: int = 80, rows: int = 24):
        self.cols = cols
        self.rows = rows
        self.shell_kind = "posix"
        self._process = None
        self._pid = None
        self._fd = None
        self._execution_results: dict[str, ExecutionResult] = {}
        self._execution_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_executions: set[str] = set()
        self._execution_lock = threading.RLock()

    def start_execution(self, command: str, context: ExecutionContext, execution_id: str) -> None:
        output = self._run_cancellable_command(command, context=context, execution_id=execution_id)
        self._execution_results[execution_id] = output

    def cancel_execution(self, execution_id: str) -> None:
        with self._execution_lock:
            self._cancelled_executions.add(execution_id)
            process = self._execution_processes.get(execution_id)
        if process is None or process.poll() is not None:
            return
        try:
            if platform.system() == "Windows":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return

    def read_execution_events(self, execution_id: str) -> list[ExecutionEvent]:
        result = self._execution_results.get(execution_id)
        if result is None:
            return []
        return [
            ExecutionEvent(execution_id=execution_id, event_type="started"),
            ExecutionEvent(execution_id=execution_id, event_type="output", text=result.output),
            ExecutionEvent(
                execution_id=execution_id,
                event_type="completed",
                text=result.output,
                completed=result.completed,
                success=result.success,
                needs_attention=result.needs_attention,
                exit_code=result.exit_code,
                completion_reason=result.completion_reason,
            ),
        ]

    def get_execution_result(self, execution_id: str) -> ExecutionResult:
        result = self._execution_results.pop(execution_id, None)
        if result is None:
            return ExecutionResult(execution_id=execution_id, output="", completed=False, success=False, needs_attention=True, completion_reason="unsupported")
        return result

    def run_command(self, command: str, context: ExecutionContext | None = None) -> ExecutionResult:
        timeout = _resolve_timeout(context)
        try:
            if platform.system() == "Windows":
                shell = _resolve_windows_shell()
                shell_name = Path(shell).name.lower()
                if "pwsh" in shell_name or shell_name == "powershell.exe":
                    completed = subprocess.run(
                        [shell, "-NoLogo", "-NoProfile", "-Command", command],
                        capture_output=True,
                        text=True,
                        cwd=_resolve_working_directory(context),
                        timeout=timeout,
                    )
                else:
                    completed = subprocess.run(
                        [shell, "/c", command],
                        capture_output=True,
                        text=True,
                        cwd=_resolve_working_directory(context),
                        timeout=timeout,
                    )
                output = f"{completed.stdout}{completed.stderr}".strip()
                return ExecutionResult(
                    execution_id="local-sync",
                    output=output,
                    completed=True,
                    success=completed.returncode == 0,
                    needs_attention=completed.returncode != 0,
                    exit_code=completed.returncode,
                    completion_reason="exit_code",
                )

            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=_resolve_working_directory(context),
                executable=os.environ.get("SHELL") or "/bin/sh",
                timeout=timeout,
            )
            output = f"{completed.stdout}{completed.stderr}".strip()
            return ExecutionResult(
                execution_id="local-sync",
                output=output,
                completed=True,
                success=completed.returncode == 0,
                needs_attention=completed.returncode != 0,
                exit_code=completed.returncode,
                completion_reason="exit_code",
            )
        except subprocess.TimeoutExpired as exc:
            return _timeout_result(command, exc)

    def _run_cancellable_command(
        self,
        command: str,
        *,
        context: ExecutionContext,
        execution_id: str,
    ) -> ExecutionResult:
        timeout = _resolve_timeout(context)
        if platform.system() == "Windows":
            shell = _resolve_windows_shell()
            shell_name = Path(shell).name.lower()
            argv = (
                [shell, "-NoLogo", "-NoProfile", "-Command", command]
                if "pwsh" in shell_name or shell_name == "powershell.exe"
                else [shell, "/c", command]
            )
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=_resolve_working_directory(context),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        else:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=_resolve_working_directory(context),
                executable=os.environ.get("SHELL") or "/bin/sh",
                start_new_session=True,
            )
        with self._execution_lock:
            self._execution_processes[execution_id] = process
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            cancelled = execution_id in self._cancelled_executions
            output = f"{stdout}{stderr}".strip()
            if cancelled:
                output = f"{output}\nCommand cancelled by operator.".strip()
            return ExecutionResult(
                execution_id=execution_id,
                output=output,
                completed=True,
                success=not cancelled and process.returncode == 0,
                needs_attention=cancelled or process.returncode != 0,
                exit_code=process.returncode,
                completion_reason="manual_stop" if cancelled else "exit_code",
            )
        except subprocess.TimeoutExpired as exc:
            self.cancel_execution(execution_id)
            process.communicate()
            result = _timeout_result(command, exc)
            result.execution_id = execution_id
            return result
        finally:
            with self._execution_lock:
                self._execution_processes.pop(execution_id, None)
                self._cancelled_executions.discard(execution_id)

    def open_interactive(self) -> str:
        if platform.system() == "Windows":
            return self._open_windows()
        return self._open_posix()

    def read(self) -> str:
        if platform.system() == "Windows":
            return self._read_windows()
        return self._read_posix()

    def write(self, data: str) -> None:
        if platform.system() == "Windows":
            if self._process is None:
                return
            self._process.write(data)
            return
        if self._fd is not None:
            os.write(self._fd, data.encode(errors="ignore"))

    def resize(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        if platform.system() == "Windows":
            self._resize_windows(cols, rows)
            return
        self._resize_posix(cols, rows)

    def close(self) -> None:
        with self._execution_lock:
            active_execution_ids = list(self._execution_processes)
        for execution_id in active_execution_ids:
            self.cancel_execution(execution_id)
        if platform.system() == "Windows":
            if self._process is not None:
                self._process.terminate()
                self._process = None
            return
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._pid is not None:
            try:
                os.kill(self._pid, 15)
                os.waitpid(self._pid, 0)
            except ChildProcessError:
                pass
            except ProcessLookupError:
                pass
            self._pid = None

    def _open_windows(self) -> str:
        try:
            winpty = __import__("winpty", fromlist=["PtyProcess"])
        except ImportError as exc:
            raise RuntimeError("pywinpty is required for local terminal sessions on Windows") from exc
        PtyProcess = winpty.PtyProcess
        shell = _resolve_windows_shell()
        shell_name = Path(shell).name.lower()
        if "pwsh" in shell_name or shell_name == "powershell.exe":
            self.shell_kind = "powershell"
        else:
            self.shell_kind = "cmd"
        self._process = PtyProcess.spawn(shell, dimensions=(self.rows, self.cols))
        return "local terminal connected"

    def _read_windows(self) -> str:
        if self._process is None:
            return ""
        try:
            return self._process.read(4096)
        except EOFError:
            return ""

    def _resize_windows(self, cols: int, rows: int) -> None:
        if self._process is None:
            return
        for method_name in ("setwinsize", "set_size", "resize"):
            method = getattr(self._process, method_name, None)
            if method is None:
                continue
            try:
                method(rows, cols)
            except TypeError:
                method(cols, rows)
            return

    def _open_posix(self) -> str:
        import pty

        shell = os.environ.get("SHELL") or "/bin/sh"
        self.shell_kind = "posix"
        env = os.environ.copy()
        # Disable some shell extensions that might cause issues in PTY
        env["ZSH_AUTOSUGGEST_MANUAL_REBIND"] = "1"
        env["TERM"] = "xterm-256color"

        self._pid, self._fd = pty.fork()
        if self._pid == 0:
            os.execvpe(shell, [shell], env)
        self._resize_posix(self.cols, self.rows)
        return "local terminal connected"

    def _read_posix(self) -> str:
        if self._fd is None:
            return ""
        readable, _, _ = select.select([self._fd], [], [], 0.05)
        if not readable:
            return ""
        try:
            return os.read(self._fd, 4096).decode(errors="ignore")
        except OSError:
            return ""

    def _resize_posix(self, cols: int, rows: int) -> None:
        if self._fd is None:
            return
        import fcntl
        import struct
        import termios

        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._fd, termios.TIOCSWINSZ, size)
