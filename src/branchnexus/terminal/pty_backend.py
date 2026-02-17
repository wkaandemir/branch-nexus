"""Pywinpty-backed PTY lifecycle for runtime-v2 terminals."""

from __future__ import annotations

import atexit
import subprocess
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.terminal.models import RuntimeKind


@dataclass(frozen=True)
class PtyHandle:
    terminal_id: str
    runtime: RuntimeKind
    command: tuple[str, ...]


PtySpawn = Callable[[list[str], str | None, dict[str, str] | None], object]


def build_shell_command(runtime: RuntimeKind, *, wsl_distribution: str = "") -> list[str]:
    if runtime == RuntimeKind.WSL:
        if wsl_distribution.strip():
            return ["wsl.exe", "-d", wsl_distribution.strip()]
        return ["wsl.exe"]
    if runtime == RuntimeKind.POWERSHELL:
        return ["powershell.exe", "-NoLogo", "-NoProfile"]
    raise BranchNexusError(
        f"Unsupported runtime kind: {runtime}",
        code=ExitCode.VALIDATION_ERROR,
        hint="Use wsl or powershell runtime.",
    )


def _spawn_with_pywinpty(command: list[str], cwd: str | None, env: dict[str, str] | None) -> object:
    try:
        from winpty import PtyProcess
    except Exception as exc:
        raise BranchNexusError(
            "pywinpty backend is unavailable.",
            code=ExitCode.RUNTIME_ERROR,
            hint="Install runtime-v2 optional dependencies on Windows.",
        ) from exc

    kwargs: dict[str, object] = {}
    if cwd:
        kwargs["cwd"] = cwd
    if env:
        kwargs["env"] = env
    return PtyProcess.spawn(subprocess.list2cmdline(command), **kwargs)


class PtyBackend:
    def __init__(self, spawn: PtySpawn | None = None) -> None:
        self._spawn = spawn or _spawn_with_pywinpty
        self._sessions: dict[str, object] = {}
        self._handles: dict[str, PtyHandle] = {}
        atexit.register(self.stop_all)

    def start(
        self,
        terminal_id: str,
        *,
        runtime: RuntimeKind,
        command: list[str] | None = None,
        wsl_distribution: str = "",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> PtyHandle:
        if terminal_id in self._sessions:
            raise BranchNexusError(
                f"Terminal already started: {terminal_id}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Stop the current PTY session before starting a new one.",
            )

        resolved_command = list(command) if command else build_shell_command(runtime, wsl_distribution=wsl_distribution)
        if not resolved_command:
            raise BranchNexusError(
                "PTY command cannot be empty.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Provide a shell command for the runtime.",
            )

        try:
            process = self._spawn(resolved_command, cwd, env)
        except BranchNexusError:
            raise
        except Exception as exc:
            raise BranchNexusError(
                "Failed to start PTY process.",
                code=ExitCode.RUNTIME_ERROR,
                hint=str(exc) or "Check runtime shell installation.",
            ) from exc

        handle = PtyHandle(
            terminal_id=terminal_id,
            runtime=runtime,
            command=tuple(resolved_command),
        )
        self._sessions[terminal_id] = process
        self._handles[terminal_id] = handle
        return handle

    def write(self, terminal_id: str, payload: str) -> None:
        process = self._require_session(terminal_id)
        try:
            process.write(payload)
        except Exception as exc:
            raise BranchNexusError(
                f"Failed to write to terminal {terminal_id}.",
                code=ExitCode.RUNTIME_ERROR,
                hint=str(exc) or "Verify terminal process health.",
            ) from exc

    def read(self, terminal_id: str, *, max_bytes: int = 4096) -> str:
        process = self._require_session(terminal_id)
        chunk: object
        try:
            chunk = process.read(max_bytes)
        except TypeError:
            chunk = process.read()
        except Exception as exc:
            raise BranchNexusError(
                f"Failed to read from terminal {terminal_id}.",
                code=ExitCode.RUNTIME_ERROR,
                hint=str(exc) or "Verify PTY stream state.",
            ) from exc

        if chunk is None:
            return ""
        if isinstance(chunk, bytes):
            return chunk.decode("utf-8", errors="replace")
        return str(chunk)

    def resize(self, terminal_id: str, *, cols: int, rows: int) -> None:
        if cols <= 0 or rows <= 0:
            raise BranchNexusError(
                f"Invalid PTY size: {cols}x{rows}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use positive terminal row/column values.",
            )
        process = self._require_session(terminal_id)
        try:
            process.set_size(cols, rows)
        except Exception as exc:
            raise BranchNexusError(
                f"Failed to resize terminal {terminal_id}.",
                code=ExitCode.RUNTIME_ERROR,
                hint=str(exc) or "Verify PTY backend supports resizing.",
            ) from exc

    def interrupt(self, terminal_id: str) -> None:
        # Ctrl+C passthrough for interactive shells.
        self.write(terminal_id, "\x03")

    def stop(self, terminal_id: str) -> None:
        process = self._sessions.pop(terminal_id, None)
        self._handles.pop(terminal_id, None)
        if process is None:
            raise BranchNexusError(
                f"Terminal not running: {terminal_id}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select an active terminal session.",
            )
        self._close_session(process)

    def stop_all(self) -> None:
        ids = list(self._sessions)
        for terminal_id in ids:
            process = self._sessions.pop(terminal_id, None)
            self._handles.pop(terminal_id, None)
            if process is None:
                continue
            self._close_session(process)

    def list_handles(self) -> list[PtyHandle]:
        return [self._handles[key] for key in sorted(self._handles)]

    def _require_session(self, terminal_id: str) -> object:
        process = self._sessions.get(terminal_id)
        if process is None:
            raise BranchNexusError(
                f"Terminal not running: {terminal_id}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Start terminal before PTY I/O operations.",
            )
        return process

    def _close_session(self, process: object) -> None:
        alive = _is_alive(process)
        if hasattr(process, "close"):
            try:
                process.close()
            except TypeError:
                process.close(True)
            except Exception:
                pass
        if alive and _is_alive(process):
            if hasattr(process, "terminate"):
                with suppress(Exception):
                    process.terminate()
            elif hasattr(process, "kill"):
                with suppress(Exception):
                    process.kill()


def _is_alive(process: object) -> bool:
    if hasattr(process, "isalive"):
        try:
            return bool(process.isalive())
        except Exception:
            return True
    return True
