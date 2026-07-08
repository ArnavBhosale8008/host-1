"""Action model shared by the agent and its executor.

The local LLM is asked to emit a small JSON object describing the next action.
Keeping the schema tiny keeps even modest local models reliable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..core.errors import AIError


class ActionType(str, Enum):
    TAP = "tap"
    TAP_ELEMENT = "tap_element"
    TEXT = "text"
    SWIPE = "swipe"
    KEY = "key"
    LAUNCH = "launch"
    WAIT = "wait"
    DONE = "done"


@dataclass(frozen=True)
class Action:
    """A single decoded agent action.

    Attributes:
        type: The kind of action.
        thought: The model's short rationale (for the activity log).
        params: Type-specific parameters (e.g. ``x``/``y`` for ``tap``).
    """

    type: ActionType
    thought: str = ""
    params: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.params is None:
            object.__setattr__(self, "params", {})


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a possibly-chatty model response."""
    text = text.strip()
    # Strip Markdown code fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        candidate = brace.group(0) if brace else None
    if candidate is None:
        raise AIError(f"No JSON object found in model output: {text[:200]!r}")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AIError(f"Model output was not valid JSON: {exc}") from exc


def parse_action(text: str) -> Action:
    """Parse a model response into an :class:`Action`.

    Raises:
        AIError: If the payload is missing/invalid or the action type unknown.
    """
    payload = _extract_json(text)
    raw_action = payload.get("action", payload)
    nested_thought = ""
    if isinstance(raw_action, str):
        raw_type = raw_action
        params: dict[str, Any] = {
            k: v for k, v in payload.items() if k not in {"action", "thought"}
        }
    elif isinstance(raw_action, dict):
        raw_type = raw_action.get("type", "")
        params = {k: v for k, v in raw_action.items() if k != "type"}
        nested_thought = str(raw_action.get("thought", ""))
    else:
        raise AIError(f"Invalid 'action' field: {raw_action!r}")

    try:
        action_type = ActionType(str(raw_type).lower())
    except ValueError as exc:
        raise AIError(f"Unknown action type: {raw_type!r}") from exc

    thought = str(payload.get("thought", nested_thought))
    return Action(type=action_type, thought=thought, params=params)
