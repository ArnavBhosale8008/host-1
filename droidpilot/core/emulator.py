"""Start, stop, and query the Android emulator process."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .adb import Adb
from .errors import EmulatorError
from .process import CommandRunner, SubprocessRunner
from .sdk import Sdk

# A launcher spawns a detached process for the emulator and returns a handle
# exposing ``poll()`` and ``terminate()`` (a subset of :class:`subprocess.Popen`).
Launcher = Callable[[Sequence[str]], "ProcessHandle"]


class ProcessHandle:
    """Minimal interface DroidPilot needs from a spawned process."""

    def poll(self) -> int | None:  # pragma: no cover - protocol definition
        ...

    def terminate(self) -> None:  # pragma: no cover - protocol definition
        ...


def _default_launcher(args: Sequence[str]) -> ProcessHandle:
    return subprocess.Popen(list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def list_avds(sdk: Sdk, runner: CommandRunner | None = None) -> list[str]:
    """Return the names of available AVDs via ``emulator -list-avds``."""
    runner = runner or SubprocessRunner()
    result = runner.run([str(sdk.emulator), "-list-avds"])
    if not result.ok:
        raise EmulatorError(f"Could not list AVDs: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def build_launch_args(
    sdk: Sdk,
    avd_name: str,
    *,
    headless: bool = False,
    no_snapshot: bool = False,
    gpu: str | None = None,
    memory_mb: int | None = None,
    cores: int | None = None,
    extra: Sequence[str] | None = None,
) -> list[str]:
    """Construct the ``emulator`` command line for ``avd_name``.

    Args:
        gpu: Value for ``-gpu`` (e.g. ``host`` for hardware acceleration,
            ``swiftshader_indirect`` for a software fallback). Omitted if ``None``.
        memory_mb: RAM for the guest in MB, passed as ``-memory``.
        cores: Number of CPU cores, passed as ``-cores``.
    """
    args = [str(sdk.emulator), "-avd", avd_name]
    if headless:
        args += ["-no-window", "-no-audio"]
    if no_snapshot:
        args.append("-no-snapshot")
    if gpu:
        args += ["-gpu", gpu]
    if memory_mb:
        args += ["-memory", str(memory_mb)]
    if cores:
        args += ["-cores", str(cores)]
    if extra:
        args += list(extra)
    return args


# Preset passed to the emulator when the user enables "Optimize for games".
GAME_MODE_GPU = "host"
GAME_MODE_MEMORY_MB = 4096
GAME_MODE_CORES = 4


@dataclass
class EmulatorSession:
    """A running (or stopping) emulator instance.

    Attributes:
        avd_name: The AVD this session was launched with.
        process: The spawned process handle.
    """

    avd_name: str
    process: ProcessHandle

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        """Terminate the emulator process if it is still running."""
        if self.is_running:
            self.process.terminate()


class EmulatorController:
    """Launches emulator sessions and waits for them to finish booting."""

    def __init__(
        self,
        sdk: Sdk,
        *,
        launcher: Launcher | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self._sdk = sdk
        self._launcher = launcher or _default_launcher
        self._runner = runner or SubprocessRunner()

    def list_avds(self) -> list[str]:
        return list_avds(self._sdk, self._runner)

    def start(
        self,
        avd_name: str,
        *,
        headless: bool = False,
        no_snapshot: bool = False,
        gpu: str | None = None,
        memory_mb: int | None = None,
        cores: int | None = None,
        extra: Sequence[str] | None = None,
    ) -> EmulatorSession:
        """Launch ``avd_name`` and return a session handle.

        Raises:
            EmulatorError: If the AVD is unknown.
        """
        available = self.list_avds()
        if avd_name not in available:
            raise EmulatorError(
                f"Unknown AVD {avd_name!r}. Available: {', '.join(available) or '<none>'}"
            )
        args = build_launch_args(
            self._sdk,
            avd_name,
            headless=headless,
            no_snapshot=no_snapshot,
            gpu=gpu,
            memory_mb=memory_mb,
            cores=cores,
            extra=extra,
        )
        return EmulatorSession(avd_name=avd_name, process=self._launcher(args))

    def wait_until_booted(
        self,
        adb: Adb,
        *,
        timeout: float = 240.0,
        poll_interval: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        """Block until the device reports ``sys.boot_completed``.

        Args:
            adb: An :class:`Adb` bound to the target device (or unbound).
            timeout: Maximum seconds to wait.
            poll_interval: Seconds between boot checks.
            sleep: Injectable sleep function (for tests).
            now: Injectable monotonic clock (for tests).

        Raises:
            EmulatorError: If the device does not boot within ``timeout``.
        """
        deadline = now() + timeout
        while now() < deadline:
            if adb.is_booted():
                return
            sleep(poll_interval)
        raise EmulatorError(f"Emulator did not finish booting within {timeout:.0f}s")
