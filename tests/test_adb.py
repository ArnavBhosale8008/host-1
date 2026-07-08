from __future__ import annotations

from pathlib import Path

import pytest

from droidpilot.core.adb import Adb, parse_devices
from droidpilot.core.errors import AdbError
from droidpilot.core.process import CommandResult

from .fakes import FakeRunner

ADB = Path("/sdk/platform-tools/adb")


def ok(stdout: str = "") -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout)


def test_parse_devices():
    output = "List of devices attached\nemulator-5554\tdevice\nfoo\toffline\n"
    devices = parse_devices(output)
    assert [d.serial for d in devices] == ["emulator-5554", "foo"]
    assert devices[0].is_ready
    assert not devices[1].is_ready


def test_tap_builds_command():
    runner = FakeRunner(lambda args: ok())
    Adb(ADB, serial="emulator-5554", runner=runner).tap(10, 20)
    assert runner.calls[0] == [
        str(ADB), "-s", "emulator-5554", "shell", "input", "tap", "10", "20",
    ]


def test_input_text_escapes_spaces():
    runner = FakeRunner(lambda args: ok())
    Adb(ADB, runner=runner).input_text("hello world")
    assert runner.calls[0][-1] == "hello%sworld"


def test_is_booted_true():
    runner = FakeRunner(lambda args: ok("1\n"))
    assert Adb(ADB, runner=runner).is_booted() is True


def test_is_booted_false_on_error():
    runner = FakeRunner(lambda args: CommandResult(returncode=1, stderr="no device"))
    assert Adb(ADB, runner=runner).is_booted() is False


def test_install_requires_success_marker():
    runner = FakeRunner(lambda args: ok("Failure [INSTALL_FAILED]"))
    with pytest.raises(AdbError):
        Adb(ADB, runner=runner).install(Path("/tmp/app.apk"))


def test_install_success():
    runner = FakeRunner(lambda args: ok("Success\n"))
    Adb(ADB, runner=runner).install(Path("/tmp/app.apk"))
    assert runner.calls[0][1:] == ["install", "-r", "/tmp/app.apk"]


def test_failed_command_raises_adberror():
    runner = FakeRunner(lambda args: CommandResult(returncode=1, stderr="boom"))
    with pytest.raises(AdbError) as excinfo:
        Adb(ADB, runner=runner).tap(1, 2)
    assert excinfo.value.stderr == "boom"


def test_screen_size_parsing():
    runner = FakeRunner(lambda args: ok("Physical size: 1080x2340\n"))
    assert Adb(ADB, runner=runner).screen_size() == (1080, 2340)


def test_list_packages_third_party():
    runner = FakeRunner(lambda args: ok("package:com.b\npackage:com.a\n"))
    assert Adb(ADB, runner=runner).list_packages() == ["com.a", "com.b"]


def test_bound_to_returns_new_instance():
    runner = FakeRunner(lambda args: ok())
    adb = Adb(ADB, runner=runner)
    bound = adb.bound_to("emulator-5556")
    assert bound.serial == "emulator-5556"
    assert adb.serial is None


def test_dump_ui_reads_back_xml():
    def handler(args):
        if "cat" in args:
            return ok("<hierarchy/>")
        return ok("UI hierchary dumped to: /sdcard/droidpilot_ui.xml")

    runner = FakeRunner(handler)
    assert Adb(ADB, runner=runner).dump_ui() == "<hierarchy/>"
