"""Reusable test doubles for DroidPilot's injectable seams."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from droidpilot.core.process import CommandResult


class FakeRunner:
    """A :class:`CommandRunner` that dispatches on the command line.

    Args:
        handler: Called with the arg list; returns a :class:`CommandResult`.
    """

    def __init__(self, handler: Callable[[list[str]], CommandResult]) -> None:
        self._handler = handler
        self.calls: list[list[str]] = []

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        input_bytes: bytes | None = None,
    ) -> CommandResult:
        call = list(args)
        self.calls.append(call)
        return self._handler(call)


class ScriptedRunner:
    """A runner returning queued results in order, recording all calls."""

    def __init__(self, results: list[CommandResult]) -> None:
        self._results = list(results)
        self.calls: list[list[str]] = []

    def run(self, args: Sequence[str], *, timeout=None, input_bytes=None) -> CommandResult:
        self.calls.append(list(args))
        if self._results:
            return self._results.pop(0)
        return CommandResult(returncode=0, stdout="", stderr="")


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self._text = text

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return self._text


class FakeHttp:
    """A minimal HTTP double for :class:`OllamaClient`."""

    def __init__(
        self,
        *,
        get_response: FakeResponse | Exception | None = None,
        post_response: FakeResponse | Exception | None = None,
    ) -> None:
        self._get = get_response
        self._post = post_response
        self.posted: list[dict[str, Any]] = []

    def get(self, url: str, *, timeout: float | None = None) -> FakeResponse:
        if isinstance(self._get, Exception):
            raise self._get
        assert self._get is not None
        return self._get

    def post(self, url: str, *, json: dict[str, Any], timeout: float | None = None) -> FakeResponse:
        self.posted.append(json)
        if isinstance(self._post, Exception):
            raise self._post
        assert self._post is not None
        return self._post
