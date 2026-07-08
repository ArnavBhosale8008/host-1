"""Runtime configuration for DroidPilot.

Configuration is resolved from (in order of precedence): explicit constructor
arguments, environment variables, then built-in defaults. Keeping this in one
place makes the rest of the codebase easy to test with injected values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1"


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


@dataclass
class Config:
    """User-facing configuration.

    Attributes:
        sdk_root: Path to the Android SDK, or ``None`` to auto-detect.
        ollama_host: Base URL of the local Ollama server.
        ollama_model: Name of the local model to use for the AI agent.
        screen_refresh_ms: Interval between live-screen frames, in milliseconds.
    """

    sdk_root: Path | None = None
    ollama_host: str = DEFAULT_OLLAMA_HOST
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    screen_refresh_ms: int = 500
    extra_env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Config:
        """Build a :class:`Config` from environment variables.

        Args:
            environ: Mapping to read from. Defaults to ``os.environ``.
        """
        env = dict(os.environ if environ is None else environ)
        sdk = env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT")
        return cls(
            sdk_root=Path(sdk) if sdk else None,
            ollama_host=_first_env("DROIDPILOT_OLLAMA_HOST") or DEFAULT_OLLAMA_HOST,
            ollama_model=env.get("DROIDPILOT_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            screen_refresh_ms=int(env.get("DROIDPILOT_SCREEN_REFRESH_MS", "500")),
        )
