"""A minimal client for a local `Ollama <https://ollama.com>`_ server.

Only the pieces DroidPilot needs are implemented: a health check, model
listing, and a single-shot chat completion. The HTTP transport is injectable so
the agent can be tested without a running server.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from ..core.errors import AIError


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...

    @property
    def text(self) -> str: ...


class HttpClient(Protocol):
    """The subset of :class:`requests.Session` used here."""

    def get(self, url: str, *, timeout: float | None = None) -> HttpResponse: ...

    def post(
        self, url: str, *, json: dict[str, Any], timeout: float | None = None
    ) -> HttpResponse: ...


class OllamaClient:
    """Talks to an Ollama server over HTTP."""

    def __init__(
        self,
        host: str,
        model: str,
        *,
        http: HttpClient | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._http = http if http is not None else self._default_http()

    @staticmethod
    def _default_http() -> HttpClient:
        import requests  # imported lazily so tests need no network stack

        return requests.Session()

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        """Return ``True`` if the server responds to a tags request."""
        try:
            response = self._http.get(f"{self._host}/api/tags", timeout=5)
        except Exception:
            return False
        return response.status_code == 200

    def list_models(self) -> list[str]:
        """Return the names of models the server has pulled."""
        try:
            response = self._http.get(f"{self._host}/api/tags", timeout=10)
        except Exception as exc:  # noqa: BLE001 - surfaced as AIError
            raise AIError(f"Could not reach Ollama at {self._host}: {exc}") from exc
        if response.status_code != 200:
            raise AIError(f"Ollama returned HTTP {response.status_code}")
        payload = response.json()
        return [model["name"] for model in payload.get("models", []) if "name" in model]

    def chat(self, system: str, user: str) -> str:
        """Send a single system+user turn and return the assistant text.

        Raises:
            AIError: On transport failure or a non-200 response.
        """
        body = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = self._http.post(
                f"{self._host}/api/chat", json=body, timeout=self._timeout
            )
        except Exception as exc:  # noqa: BLE001
            raise AIError(f"Ollama chat request failed: {exc}") from exc
        if response.status_code != 200:
            raise AIError(f"Ollama chat returned HTTP {response.status_code}: {response.text}")
        payload = response.json()
        try:
            return payload["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise AIError(f"Unexpected Ollama response shape: {json.dumps(payload)[:200]}") from exc
