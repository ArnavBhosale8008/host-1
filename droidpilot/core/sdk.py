"""Locate the Android SDK and its tools across platforms.

Discovery is intentionally split into small, pure helpers so it can be unit
tested without a real SDK installed. The public entry point is
:func:`locate_sdk`, which returns a :class:`Sdk` describing where the important
executables live.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .errors import SdkNotFoundError

# A function that reports whether a path exists. Injectable for testing.
ExistsFn = Callable[[Path], bool]


def _exe(name: str) -> str:
    """Return the platform-appropriate executable file name."""
    return f"{name}.exe" if platform.system() == "Windows" else name


def default_sdk_candidates(environ: dict[str, str] | None = None) -> list[Path]:
    """Return candidate SDK root directories, most specific first.

    Args:
        environ: Environment mapping to read. Defaults to ``os.environ``.
    """
    env = dict(os.environ if environ is None else environ)
    candidates: list[Path] = []
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = env.get(var)
        if value:
            candidates.append(Path(value))

    home = Path(env.get("HOME") or env.get("USERPROFILE") or "~").expanduser()
    system = platform.system()
    if system == "Darwin":
        candidates.append(home / "Library" / "Android" / "sdk")
    elif system == "Windows":
        local = env.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Android" / "Sdk")
    candidates.append(home / "Android" / "Sdk")

    # De-duplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


@dataclass(frozen=True)
class Sdk:
    """Describes a located Android SDK.

    Attributes:
        root: The SDK root directory.
        adb: Path to the ``adb`` executable.
        emulator: Path to the ``emulator`` executable.
        avdmanager: Path to the ``avdmanager`` executable, if present.
    """

    root: Path
    adb: Path
    emulator: Path
    avdmanager: Path | None

    @property
    def has_avdmanager(self) -> bool:
        return self.avdmanager is not None


def _find_tool(root: Path, relative_options: list[Path], exists: ExistsFn) -> Path | None:
    for rel in relative_options:
        candidate = root / rel
        if exists(candidate):
            return candidate
    return None


def sdk_from_root(root: Path, exists: ExistsFn = Path.exists) -> Sdk | None:
    """Build an :class:`Sdk` from a root dir, or ``None`` if tools are missing.

    Args:
        root: Candidate SDK root.
        exists: Predicate used to check for files (injectable for tests).
    """
    adb = _find_tool(root, [Path("platform-tools") / _exe("adb")], exists)
    emulator = _find_tool(
        root,
        [Path("emulator") / _exe("emulator"), Path("tools") / _exe("emulator")],
        exists,
    )
    if adb is None or emulator is None:
        return None
    avdmanager = _find_tool(
        root,
        [
            Path("cmdline-tools") / "latest" / "bin" / _exe("avdmanager"),
            Path("tools") / "bin" / _exe("avdmanager"),
        ],
        exists,
    )
    return Sdk(root=root, adb=adb, emulator=emulator, avdmanager=avdmanager)


def locate_sdk(
    explicit_root: Path | None = None,
    *,
    environ: dict[str, str] | None = None,
    exists: ExistsFn = Path.exists,
) -> Sdk:
    """Locate a usable Android SDK.

    Args:
        explicit_root: A user-provided SDK root to try first.
        environ: Environment mapping. Defaults to ``os.environ``.
        exists: Predicate used to check for files (injectable for tests).

    Raises:
        SdkNotFoundError: If no candidate directory contains ``adb`` +
            ``emulator``.
    """
    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(explicit_root)
    candidates.extend(default_sdk_candidates(environ))

    tried: list[str] = []
    for root in candidates:
        tried.append(str(root))
        sdk = sdk_from_root(root, exists=exists)
        if sdk is not None:
            return sdk

    raise SdkNotFoundError(
        "Could not find an Android SDK with platform-tools + emulator. "
        "Set ANDROID_HOME or install the SDK. Tried: " + ", ".join(tried or ["<none>"])
    )
