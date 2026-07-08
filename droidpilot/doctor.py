"""Environment diagnostics for DroidPilot (``droidpilot doctor``)."""

from __future__ import annotations

from dataclasses import dataclass

from .ai.ollama_client import OllamaClient
from .config import Config
from .core.emulator import list_avds
from .core.errors import DroidPilotError
from .core.sdk import Sdk, locate_sdk


@dataclass
class Check:
    """A single diagnostic result."""

    name: str
    ok: bool
    detail: str

    def format(self) -> str:
        mark = "OK " if self.ok else "!! "
        return f"[{mark}] {self.name}: {self.detail}"


def run_checks(config: Config | None = None) -> list[Check]:
    """Run all environment checks and return their results."""
    config = config or Config.from_env()
    checks: list[Check] = []

    sdk: Sdk | None = None
    try:
        sdk = locate_sdk(config.sdk_root)
        checks.append(Check("Android SDK", True, str(sdk.root)))
        checks.append(Check("adb", True, str(sdk.adb)))
        checks.append(Check("emulator", True, str(sdk.emulator)))
    except DroidPilotError as exc:
        checks.append(Check("Android SDK", False, str(exc)))

    if sdk is not None:
        try:
            avds = list_avds(sdk)
            detail = ", ".join(avds) if avds else "no AVDs created yet"
            checks.append(Check("AVDs", bool(avds), detail))
        except DroidPilotError as exc:
            checks.append(Check("AVDs", False, str(exc)))

    client = OllamaClient(config.ollama_host, config.ollama_model)
    if client.is_available():
        try:
            models = client.list_models()
        except DroidPilotError:
            models = []
        has_model = config.ollama_model in models or any(
            m.split(":")[0] == config.ollama_model for m in models
        )
        detail = f"{config.ollama_host} (models: {', '.join(models) or 'none'})"
        checks.append(Check("Ollama (local AI)", has_model, detail))
    else:
        checks.append(
            Check("Ollama (local AI)", False, f"not reachable at {config.ollama_host}")
        )

    return checks


def format_report(checks: list[Check]) -> str:
    """Render checks as a human-readable multi-line report."""
    return "\n".join(check.format() for check in checks)
