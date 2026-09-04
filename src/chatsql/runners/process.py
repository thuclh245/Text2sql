"""Subprocess runner for isolated baseline execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from chatsql.runners.base import BaseRunner


class ProcessRunner(BaseRunner):
    """Executes commands in a subprocess with isolation."""

    def run(
        self,
        command: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> tuple[int, str, str]:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            return completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return -1, stdout, f"Process timed out after {timeout_seconds}s: {stderr}"
        except Exception as exc:
            return -1, "", f"Failed to execute process: {exc}"
