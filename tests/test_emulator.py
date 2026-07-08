from __future__ import annotations

from pathlib import Path

import pytest

from droidpilot.core.adb import Adb
from droidpilot.core.emulator import EmulatorController, build_launch_args, list_avds
from droidpilot.core.errors import EmulatorError
from droidpilot.core.process import CommandResult
from droidpilot.core.sdk import Sdk

from .fakes import FakeRunner

SDK = Sdk(
    root=Path("/sdk"),
    adb=Path("/sdk/platform-tools/adb"),
    emulator=Path("/sdk/emulator/emulator"),
    avdmanager=None,
)


class FakeProcess:
    def __init__(self) -> None:
        self._alive = True
        self.terminated = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False


def test_build_launch_args_headless():
    args = build_launch_args(SDK, "Pixel", headless=True, no_snapshot=True)
    assert "-no-window" in args and "-no-snapshot" in args
    assert args[:3] == [str(SDK.emulator), "-avd", "Pixel"]


def test_build_launch_args_game_mode_flags():
    args = build_launch_args(SDK, "Pixel", gpu="host", memory_mb=4096, cores=4)
    assert args[args.index("-gpu") + 1] == "host"
    assert args[args.index("-memory") + 1] == "4096"
    assert args[args.index("-cores") + 1] == "4"


def test_build_launch_args_omits_perf_flags_by_default():
    args = build_launch_args(SDK, "Pixel")
    assert "-gpu" not in args and "-memory" not in args and "-cores" not in args


def test_list_avds_parses_lines():
    runner = FakeRunner(lambda a: CommandResult(returncode=0, stdout="Pixel_6\nTablet\n"))
    assert list_avds(SDK, runner) == ["Pixel_6", "Tablet"]


def test_list_avds_error():
    runner = FakeRunner(lambda a: CommandResult(returncode=1, stderr="boom"))
    with pytest.raises(EmulatorError):
        list_avds(SDK, runner)


def test_start_unknown_avd_raises():
    runner = FakeRunner(lambda a: CommandResult(returncode=0, stdout="Pixel_6\n"))
    controller = EmulatorController(SDK, launcher=lambda a: FakeProcess(), runner=runner)
    with pytest.raises(EmulatorError):
        controller.start("DoesNotExist")


def test_start_returns_running_session():
    runner = FakeRunner(lambda a: CommandResult(returncode=0, stdout="Pixel_6\n"))
    proc = FakeProcess()
    controller = EmulatorController(SDK, launcher=lambda a: proc, runner=runner)
    session = controller.start("Pixel_6")
    assert session.is_running
    session.stop()
    assert proc.terminated


def test_wait_until_booted_success():
    booted = {"n": 0}

    def handler(args):
        booted["n"] += 1
        value = "1" if booted["n"] >= 3 else "0"
        return CommandResult(returncode=0, stdout=value)

    adb = Adb(SDK.adb, runner=FakeRunner(handler))
    controller = EmulatorController(SDK, runner=FakeRunner(lambda a: CommandResult(0)))
    controller.wait_until_booted(adb, timeout=100, poll_interval=1, sleep=lambda s: None)


def test_wait_until_booted_times_out():
    adb = Adb(SDK.adb, runner=FakeRunner(lambda a: CommandResult(0, stdout="0")))
    controller = EmulatorController(SDK, runner=FakeRunner(lambda a: CommandResult(0)))
    clock = {"t": 0.0}

    def now():
        clock["t"] += 5
        return clock["t"]

    with pytest.raises(EmulatorError):
        controller.wait_until_booted(
            adb, timeout=10, poll_interval=1, sleep=lambda s: None, now=now
        )
