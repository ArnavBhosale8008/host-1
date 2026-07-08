"""Exception types used across DroidPilot."""

from __future__ import annotations


class DroidPilotError(Exception):
    """Base class for all DroidPilot errors."""


class SdkNotFoundError(DroidPilotError):
    """Raised when the Android SDK (or a required component) cannot be located."""


class AdbError(DroidPilotError):
    """Raised when an ``adb`` command fails."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class EmulatorError(DroidPilotError):
    """Raised when the emulator process cannot be started or does not boot."""


class AIError(DroidPilotError):
    """Raised when the local AI backend is unavailable or returns an invalid response."""
