from __future__ import annotations

from pathlib import Path

import pytest

from droidpilot.core.errors import SdkNotFoundError
from droidpilot.core.sdk import default_sdk_candidates, locate_sdk, sdk_from_root


def _fake_sdk_layout(root: Path) -> set[Path]:
    return {
        root / "platform-tools" / "adb",
        root / "emulator" / "emulator",
        root / "cmdline-tools" / "latest" / "bin" / "avdmanager",
    }


def test_default_candidates_prefers_env(monkeypatch):
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    candidates = default_sdk_candidates({"ANDROID_HOME": "/opt/sdk", "HOME": "/home/x"})
    assert candidates[0] == Path("/opt/sdk")


def test_default_candidates_dedupes():
    env = {"ANDROID_HOME": "/opt/sdk", "ANDROID_SDK_ROOT": "/opt/sdk", "HOME": "/home/x"}
    candidates = default_sdk_candidates(env)
    assert candidates.count(Path("/opt/sdk")) == 1


def test_sdk_from_root_found():
    root = Path("/opt/sdk")
    existing = _fake_sdk_layout(root)
    sdk = sdk_from_root(root, exists=lambda p: p in existing)
    assert sdk is not None
    assert sdk.adb == root / "platform-tools" / "adb"
    assert sdk.has_avdmanager


def test_sdk_from_root_missing_emulator_returns_none():
    root = Path("/opt/sdk")
    existing = {root / "platform-tools" / "adb"}
    assert sdk_from_root(root, exists=lambda p: p in existing) is None


def test_sdk_from_root_without_avdmanager():
    root = Path("/opt/sdk")
    existing = {root / "platform-tools" / "adb", root / "emulator" / "emulator"}
    sdk = sdk_from_root(root, exists=lambda p: p in existing)
    assert sdk is not None
    assert sdk.avdmanager is None
    assert not sdk.has_avdmanager


def test_locate_sdk_uses_explicit_root_first():
    good = Path("/custom/sdk")
    existing = _fake_sdk_layout(good)
    sdk = locate_sdk(good, environ={}, exists=lambda p: p in existing)
    assert sdk.root == good


def test_locate_sdk_raises_when_missing():
    with pytest.raises(SdkNotFoundError):
        locate_sdk(Path("/nope"), environ={}, exists=lambda p: False)
