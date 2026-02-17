"""WSL script execution utilities."""

from __future__ import annotations

import logging as py_logging
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.ui.runtime.constants import (
    COMMAND_HEARTBEAT_SECONDS,
    WSL_PREFLIGHT_TIMEOUT_SECONDS,
)
from branchnexus.ui.services.security import (
    command_for_log,
    sanitize_terminal_log_text,
    truncate_log,
)

logger = py_logging.getLogger(__name__)


def _format_terminal_progress_line(level: str, step: str, message: str) -> str:
    stamp = datetime.now().strftime("%H:%M:%S")
    step_name = step.strip() or "runtime"
    detail = sanitize_terminal_log_text(message)
    return f"[BranchNexus][{stamp}][{level}] {step_name}: {detail}"


def emit_terminal_progress(
    sink: Callable[[str], None] | None,
    *,
    level: str,
    step: str,
    message: str,
) -> None:
    """Emit a formatted progress line to sink when available."""
    if sink is None:
        return
    sink(_format_terminal_progress_line(level, step, message))


def run_with_heartbeat(
    *,
    command: list[str],
    env: dict[str, str] | None,
    timeout_seconds: int,
    step: str,
    input_text: str | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run subprocess with heartbeat progress lines until completion."""
    holder: dict[str, subprocess.CompletedProcess[str]] = {}
    error: dict[str, BaseException] = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            holder["result"] = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                input=input_text,
                timeout=timeout_seconds,
            )
        except BaseException as exc:  # pragma: no cover - passthrough
            error["exc"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    started = time.monotonic()
    next_heartbeat = COMMAND_HEARTBEAT_SECONDS
    while not done.wait(timeout=1):
        elapsed = int(time.monotonic() - started)
        if elapsed >= next_heartbeat:
            emit_terminal_progress(
                verbose_sink,
                level="WAIT",
                step=step,
                message=f"still running elapsed={elapsed}s timeout={timeout_seconds}s",
            )
            next_heartbeat += COMMAND_HEARTBEAT_SECONDS

    if error:
        raise error["exc"]

    result = holder.get("result")
    if result is not None:
        return result
    raise BranchNexusError(
        f"Runtime komutu sonuc donmedi: {step}",
        code=ExitCode.RUNTIME_ERROR,
        hint="Runtime komut loglarini kontrol edin.",
    )


def run_wsl_probe_script(
    *,
    distribution: str,
    script: str,
    step: str,
    user: str = "",
    input_text: str | None = None,
    timeout_seconds: int | None = None,
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a WSL bash probe script and convert timeout errors."""
    resolved_user = user.strip()
    if resolved_user:
        command = ["wsl.exe", "-d", distribution, "-u", resolved_user, "--", "bash", "-lc", script]
    else:
        command = build_wsl_command(distribution, ["bash", "-lc", script])
    emit_terminal_progress(
        verbose_sink,
        level="RUN",
        step=step,
        message=f"command={command_for_log(command)}",
    )
    effective_timeout = timeout_seconds or WSL_PREFLIGHT_TIMEOUT_SECONDS
    try:
        result = run_with_heartbeat(
            command=command,
            env=env,
            timeout_seconds=effective_timeout,
            step=step,
            input_text=input_text,
            verbose_sink=verbose_sink,
        )
    except subprocess.TimeoutExpired as exc:
        emit_terminal_progress(
            verbose_sink,
            level="TIMEOUT",
            step=step,
            message=f"timeout={effective_timeout}s",
        )
        raise BranchNexusError(
            f"Runtime WSL hazirlik adimi zaman asimina ugradi: {step}",
            code=ExitCode.RUNTIME_ERROR,
            hint="Komut beklenenden uzun surdu. WSL durumunu ve ag baglantisini kontrol edin.",
        ) from exc

    level = "OK" if result.returncode == 0 else "WARN"
    detail = (result.stderr or result.stdout or "").strip()
    message = f"exit={result.returncode}"
    if detail:
        message = f"exit={result.returncode} output={truncate_log(detail, limit=220)}"
    emit_terminal_progress(verbose_sink, level=level, step=step, message=message)
    return result


def run_wsl_script(
    *,
    distribution: str,
    script: str,
    step: str,
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a WSL script and raise a typed runtime error on failures."""
    command = build_wsl_command(distribution, ["bash", "-lc", script])
    logger.debug("runtime-open preflight-run step=%s command=%s", step, command_for_log(command))
    emit_terminal_progress(
        verbose_sink,
        level="RUN",
        step=step,
        message=f"command={command_for_log(command)}",
    )
    try:
        result = run_with_heartbeat(
            command=command,
            env=env,
            timeout_seconds=WSL_PREFLIGHT_TIMEOUT_SECONDS,
            step=step,
            verbose_sink=verbose_sink,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(
            "runtime-open preflight-timeout step=%s timeout=%ss",
            step,
            WSL_PREFLIGHT_TIMEOUT_SECONDS,
        )
        emit_terminal_progress(
            verbose_sink,
            level="TIMEOUT",
            step=step,
            message=f"timeout={WSL_PREFLIGHT_TIMEOUT_SECONDS}s",
        )
        raise BranchNexusError(
            f"Runtime WSL hazirlik adimi zaman asimina ugradi: {step}",
            code=ExitCode.RUNTIME_ERROR,
            hint=(
                "Komut beklenenden uzun surdu. "
                "WSL durumunu, ag baglantisini ve git kimlik ayarlarini kontrol edin."
            ),
        ) from exc
    if result.returncode == 0:
        logger.debug("runtime-open preflight-ok step=%s stdout=%s", step, truncate_log(result.stdout))
        emit_terminal_progress(verbose_sink, level="OK", step=step, message="command completed")
        return result
    logger.error(
        "runtime-open preflight-fail step=%s code=%s stderr=%s",
        step,
        result.returncode,
        truncate_log(result.stderr),
    )
    emit_terminal_progress(
        verbose_sink,
        level="FAIL",
        step=step,
        message=f"code={result.returncode} stderr={truncate_log(result.stderr, limit=220)}",
    )
    raise BranchNexusError(
        f"Runtime WSL hazirlik adimi basarisiz: {step}",
        code=ExitCode.RUNTIME_ERROR,
        hint=result.stderr.strip() or "WSL git/tmux komutlarini kontrol edin.",
    )
