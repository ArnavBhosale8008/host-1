"""A small, injectable command runner abstraction.

The rest of the code never calls :mod:`subprocess` directly; instead it goes
through a :class:`CommandRunner`. Tests supply a fake runner, so no real
processes are spawned.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    """Result of running a command.

    Attributes:
        returncode: Process exit code.
        stdout: Captured standard output (text).
        stderr: Captured standard error (text).
    """

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandRunner(Protocol):
    """Runs a command and returns its result."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        input_bytes: bytes | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    """Default :class:`CommandRunner` backed by :mod:`subprocess`."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        input_bytes: bytes | None = None,
    ) -> CommandResult:
        completed = subprocess.run(  # noqa: S603 - args are constructed internally
            list(args),
            capture_output=True,
            timeout=timeout,
            input=input_bytes,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout.decode("utf-8", errors="replace"),
            stderr=completed.stderr.decode("utf-8", errors="replace"),
        )

    def run_binary(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> tuple[int, bytes, bytes]:
        """Run a command and return raw ``(returncode, stdout, stderr)`` bytes.

        Used for binary payloads such as PNG screenshots.
        """
        completed = subprocess.run(  # noqa: S603
            list(args), capture_output=True, timeout=timeout
        )
        return completed.returncode, completed.stdout, completed.stderr
