from __future__ import annotations

from pathlib import Path

import droidpilot.doctor as doctor
from droidpilot.config import Config
from droidpilot.core.errors import SdkNotFoundError
from droidpilot.core.sdk import Sdk

SDK = Sdk(
    root=Path("/sdk"),
    adb=Path("/sdk/platform-tools/adb"),
    emulator=Path("/sdk/emulator/emulator"),
    avdmanager=Path("/sdk/cmdline-tools/latest/bin/avdmanager"),
)


class FakeClient:
    def __init__(self, available: bool, models: list[str]) -> None:
        self._available = available
        self._models = models

    def is_available(self) -> bool:
        return self._available

    def list_models(self) -> list[str]:
        return self._models


def test_run_checks_all_ok(monkeypatch):
    monkeypatch.setattr(doctor, "locate_sdk", lambda root: SDK)
    monkeypatch.setattr(doctor, "list_avds", lambda sdk: ["Pixel_6"])
    monkeypatch.setattr(doctor, "OllamaClient", lambda h, m: FakeClient(True, ["llama3.1"]))
    checks = doctor.run_checks(Config(ollama_model="llama3.1"))
    assert all(c.ok for c in checks)
    names = {c.name for c in checks}
    assert {"Android SDK", "adb", "emulator", "AVDs", "Ollama (local AI)"} <= names


def test_run_checks_missing_sdk(monkeypatch):
    def raise_sdk(root):
        raise SdkNotFoundError("nope")

    monkeypatch.setattr(doctor, "locate_sdk", raise_sdk)
    monkeypatch.setattr(doctor, "OllamaClient", lambda h, m: FakeClient(False, []))
    checks = doctor.run_checks(Config())
    sdk_check = next(c for c in checks if c.name == "Android SDK")
    assert not sdk_check.ok
    # No AVD check should be produced when the SDK is missing.
    assert not any(c.name == "AVDs" for c in checks)


def test_run_checks_ollama_missing_model(monkeypatch):
    monkeypatch.setattr(doctor, "locate_sdk", lambda root: SDK)
    monkeypatch.setattr(doctor, "list_avds", lambda sdk: [])
    monkeypatch.setattr(doctor, "OllamaClient", lambda h, m: FakeClient(True, ["other"]))
    checks = doctor.run_checks(Config(ollama_model="llama3.1"))
    ollama = next(c for c in checks if c.name == "Ollama (local AI)")
    assert not ollama.ok
