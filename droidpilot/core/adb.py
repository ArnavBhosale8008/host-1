"""A thin, typed wrapper around the ``adb`` command-line tool.

Every method funnels through an injected :class:`CommandRunner`, so behaviour
can be verified in tests without a device or a real ``adb`` binary.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import AdbError
from .process import CommandResult, CommandRunner, SubprocessRunner

# Android key event codes used by :meth:`Adb.key_event` convenience wrappers.
KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_APP_SWITCH = 187
KEYCODE_ENTER = 66


@dataclass(frozen=True)
class Device:
    """A connected device/emulator as reported by ``adb devices``.

    Attributes:
        serial: The device serial (e.g. ``emulator-5554``).
        state: Connection state (``device``, ``offline``, ``unauthorized``...).
    """

    serial: str
    state: str

    @property
    def is_ready(self) -> bool:
        return self.state == "device"


def parse_devices(output: str) -> list[Device]:
    """Parse the output of ``adb devices`` into :class:`Device` objects."""
    devices: list[Device] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append(Device(serial=parts[0], state=parts[1]))
    return devices


class Adb:
    """Wrapper around a specific ``adb`` executable, optionally bound to a device."""

    def __init__(
        self,
        adb_path: Path,
        *,
        serial: str | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self._adb_path = adb_path
        self._serial = serial
        self._runner = runner or SubprocessRunner()

    @property
    def serial(self) -> str | None:
        return self._serial

    def bound_to(self, serial: str) -> Adb:
        """Return a copy of this wrapper bound to ``serial``."""
        return Adb(self._adb_path, serial=serial, runner=self._runner)

    def _base(self) -> list[str]:
        cmd = [str(self._adb_path)]
        if self._serial:
            cmd += ["-s", self._serial]
        return cmd

    def _run(
        self, args: Sequence[str], *, timeout: float | None = None, check: bool = True
    ) -> CommandResult:
        result = self._runner.run(self._base() + list(args), timeout=timeout)
        if check and not result.ok:
            raise AdbError(
                f"adb {' '.join(args)} failed", returncode=result.returncode, stderr=result.stderr
            )
        return result

    # -- Discovery -----------------------------------------------------------
    def devices(self) -> list[Device]:
        """Return the list of connected devices."""
        return parse_devices(self._run(["devices"]).stdout)

    def is_booted(self) -> bool:
        """Return ``True`` once ``sys.boot_completed`` is set on the device."""
        result = self._run(["shell", "getprop", "sys.boot_completed"], check=False)
        return result.ok and result.stdout.strip() == "1"

    def wait_for_device(self, timeout: float = 120.0) -> None:
        """Block until the device appears (``adb wait-for-device``)."""
        self._run(["wait-for-device"], timeout=timeout)

    # -- Input ---------------------------------------------------------------
    def tap(self, x: int, y: int) -> None:
        """Tap the screen at pixel ``(x, y)``."""
        self._run(["shell", "input", "tap", str(x), str(y)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe from ``(x1, y1)`` to ``(x2, y2)`` over ``duration_ms``."""
        self._run(
            ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)]
        )

    def input_text(self, text: str) -> None:
        """Type ``text`` into the focused field (spaces are escaped)."""
        escaped = text.replace(" ", "%s")
        self._run(["shell", "input", "text", escaped])

    def key_event(self, keycode: int) -> None:
        """Send a hardware/soft key event by Android key code."""
        self._run(["shell", "input", "keyevent", str(keycode)])

    def press_home(self) -> None:
        self.key_event(KEYCODE_HOME)

    def press_back(self) -> None:
        self.key_event(KEYCODE_BACK)

    # -- Apps ----------------------------------------------------------------
    def install(self, apk_path: Path, *, reinstall: bool = True) -> None:
        """Install an APK, replacing an existing install by default."""
        args = ["install"]
        if reinstall:
            args.append("-r")
        args.append(str(apk_path))
        result = self._run(args, timeout=300)
        if "Success" not in result.stdout:
            raise AdbError(f"install did not report success: {result.stdout.strip()}")

    def uninstall(self, package: str) -> None:
        """Uninstall an app by package name."""
        self._run(["uninstall", package])

    def list_packages(self, *, third_party_only: bool = True) -> list[str]:
        """Return installed package names."""
        args = ["shell", "pm", "list", "packages"]
        if third_party_only:
            args.append("-3")
        out = self._run(args).stdout
        return sorted(line.replace("package:", "").strip() for line in out.splitlines() if line)

    def launch(self, package: str) -> None:
        """Launch an app by package name using its default launcher activity."""
        self._run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])

    # -- Introspection -------------------------------------------------------
    def screencap_png(self) -> bytes:
        """Capture a screenshot and return raw PNG bytes."""
        runner = self._runner
        args = self._base() + ["exec-out", "screencap", "-p"]
        if isinstance(runner, SubprocessRunner):
            code, stdout, stderr = runner.run_binary(args, timeout=30)
            if code != 0:
                raise AdbError("screencap failed", returncode=code, stderr=stderr.decode("replace"))
            return stdout
        # Fallback for injected runners: bytes are round-tripped via latin-1.
        result = runner.run(args, timeout=30)
        if not result.ok:
            raise AdbError("screencap failed", returncode=result.returncode, stderr=result.stderr)
        return result.stdout.encode("latin-1")

    def dump_ui(self) -> str:
        """Return the current UI hierarchy as an XML string.

        Uses ``uiautomator dump`` to a temp file on the device, then reads it
        back. Returns the raw XML for :mod:`droidpilot.core.uihierarchy`.
        """
        remote = "/sdcard/droidpilot_ui.xml"
        dump = self._run(["shell", "uiautomator", "dump", remote], check=False)
        if not dump.ok and "dumped to" not in dump.stdout:
            raise AdbError("uiautomator dump failed", stderr=dump.stderr or dump.stdout)
        return self._run(["shell", "cat", remote]).stdout

    def screen_size(self) -> tuple[int, int]:
        """Return the device screen size ``(width, height)`` in pixels."""
        out = self._run(["shell", "wm", "size"]).stdout
        match = re.search(r"(\d+)x(\d+)", out)
        if not match:
            raise AdbError(f"Could not parse screen size from: {out.strip()!r}")
        return int(match.group(1)), int(match.group(2))

    def current_focus(self) -> str | None:
        """Return the currently focused window/activity string, if available."""
        result = self._run(["shell", "dumpsys", "window", "windows"], check=False)
        if not result.ok:
            return None
        match = re.search(r"mCurrentFocus=\S+ \S+ (\S+)}", result.stdout)
        return match.group(1) if match else None
