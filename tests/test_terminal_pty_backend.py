from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.terminal import PtyBackend, RuntimeKind, build_shell_command


class _FakePty:
    def __init__(self, chunks: list[str] | None = None, *, sticky_alive: bool = False) -> None:
        self.chunks = list(chunks or [])
        self.writes: list[str] = []
        self.size: tuple[int, int] | None = None
        self.closed = False
        self.terminated = False
        self.sticky_alive = sticky_alive

    def write(self, payload: str) -> None:
        self.writes.append(payload)

    def read(self, _size: int = 4096) -> str:
        if self.chunks:
            return self.chunks.pop(0)
        return ""

    def set_size(self, cols: int, rows: int) -> None:
        self.size = (cols, rows)

    def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.terminated = True

    def isalive(self) -> bool:
        if self.sticky_alive:
            return not self.terminated
        return not self.closed


def test_build_shell_command_supports_wsl_and_powershell() -> None:
    assert build_shell_command(RuntimeKind.WSL) == ["wsl.exe"]
    assert build_shell_command(RuntimeKind.WSL, wsl_distribution="Ubuntu") == ["wsl.exe", "-d", "Ubuntu"]
    assert build_shell_command(RuntimeKind.POWERSHELL) == ["powershell.exe", "-NoLogo", "-NoProfile"]


def test_backend_starts_and_lists_handles() -> None:
    seen: list[list[str]] = []

    def spawn(command: list[str], _cwd: str | None, _env: dict[str, str] | None) -> _FakePty:
        seen.append(command)
        return _FakePty()

    backend = PtyBackend(spawn=spawn)
    backend.start("t1", runtime=RuntimeKind.WSL, wsl_distribution="Ubuntu")
    backend.start("t2", runtime=RuntimeKind.POWERSHELL)

    assert seen[0] == ["wsl.exe", "-d", "Ubuntu"]
    assert seen[1] == ["powershell.exe", "-NoLogo", "-NoProfile"]
    assert [handle.terminal_id for handle in backend.list_handles()] == ["t1", "t2"]


def test_backend_write_read_resize_and_interrupt() -> None:
    pty = _FakePty(chunks=["hello", ""])
    backend = PtyBackend(spawn=lambda _c, _cwd, _env: pty)
    backend.start("t1", runtime=RuntimeKind.WSL)

    backend.write("t1", "echo test\n")
    backend.interrupt("t1")
    backend.resize("t1", cols=120, rows=40)

    assert backend.read("t1") == "hello"
    assert pty.writes == ["echo test\n", "\x03"]
    assert pty.size == (120, 40)


def test_backend_rejects_duplicate_starts_and_missing_sessions() -> None:
    backend = PtyBackend(spawn=lambda _c, _cwd, _env: _FakePty())
    backend.start("t1", runtime=RuntimeKind.WSL)

    with pytest.raises(BranchNexusError):
        backend.start("t1", runtime=RuntimeKind.WSL)
    with pytest.raises(BranchNexusError):
        backend.read("missing")


def test_backend_stop_and_stop_all_close_orphan_processes() -> None:
    spawned: list[_FakePty] = []

    def spawn(_command: list[str], _cwd: str | None, _env: dict[str, str] | None) -> _FakePty:
        instance = _FakePty(sticky_alive=True)
        spawned.append(instance)
        return instance

    backend = PtyBackend(spawn=spawn)
    backend.start("t1", runtime=RuntimeKind.WSL)
    backend.start("t2", runtime=RuntimeKind.POWERSHELL)

    backend.stop("t1")
    assert spawned[0].closed is True
    assert spawned[0].terminated is True

    backend.stop_all()
    assert spawned[1].closed is True
    assert spawned[1].terminated is True


def test_backend_validates_resize_values() -> None:
    backend = PtyBackend(spawn=lambda _c, _cwd, _env: _FakePty())
    backend.start("t1", runtime=RuntimeKind.WSL)
    with pytest.raises(BranchNexusError):
        backend.resize("t1", cols=0, rows=20)
