"""The AI agent loop: turn a natural-language goal into device actions."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ..core.adb import KEYCODE_APP_SWITCH, KEYCODE_BACK, KEYCODE_ENTER, KEYCODE_HOME, Adb
from ..core.errors import AIError
from ..core.uihierarchy import UiNode, interactable_nodes, parse_hierarchy, summarize
from .actions import Action, ActionType, parse_action
from .ollama_client import OllamaClient
from .prompts import SYSTEM_PROMPT, build_user_prompt

_KEY_NAMES = {
    "back": KEYCODE_BACK,
    "home": KEYCODE_HOME,
    "enter": KEYCODE_ENTER,
    "recents": KEYCODE_APP_SWITCH,
}


@dataclass
class AgentStep:
    """One step of an agent run, for logging/UI display."""

    index: int
    action: Action
    detail: str


class ActionExecutor:
    """Applies :class:`Action` objects to a device via :class:`Adb`."""

    def __init__(self, adb: Adb, *, sleep: Callable[[float], None] = time.sleep) -> None:
        self._adb = adb
        self._sleep = sleep

    def execute(self, action: Action, nodes: list[UiNode]) -> str:
        """Execute ``action`` and return a human-readable description.

        Args:
            action: The action to perform.
            nodes: The interactable nodes from the current screen, used to
                resolve ``tap_element`` indices to coordinates.

        Raises:
            AIError: If the action's parameters are invalid.
        """
        params = action.params
        if action.type is ActionType.TAP:
            x, y = int(params["x"]), int(params["y"])
            self._adb.tap(x, y)
            return f"tapped ({x},{y})"
        if action.type is ActionType.TAP_ELEMENT:
            index = int(params["index"])
            if not 0 <= index < len(nodes):
                raise AIError(f"tap_element index {index} out of range (0..{len(nodes) - 1})")
            node = nodes[index]
            assert node.bounds is not None
            x, y = node.bounds.center
            self._adb.tap(x, y)
            return f'tapped element [{index}] "{node.label}" at ({x},{y})'
        if action.type is ActionType.TEXT:
            value = str(params.get("value", params.get("text", "")))
            self._adb.input_text(value)
            return f"typed {value!r}"
        if action.type is ActionType.KEY:
            name = str(params.get("name", "")).lower()
            if name not in _KEY_NAMES:
                raise AIError(f"Unknown key name: {name!r}")
            self._adb.key_event(_KEY_NAMES[name])
            return f"pressed {name}"
        if action.type is ActionType.SWIPE:
            return self._swipe(str(params.get("direction", "up")).lower())
        if action.type is ActionType.LAUNCH:
            package = str(params["package"])
            self._adb.launch(package)
            return f"launched {package}"
        if action.type is ActionType.WAIT:
            seconds = float(params.get("seconds", 1))
            self._sleep(seconds)
            return f"waited {seconds}s"
        if action.type is ActionType.DONE:
            return str(params.get("summary", "done"))
        raise AIError(f"Unhandled action type: {action.type}")  # pragma: no cover

    def _swipe(self, direction: str) -> str:
        width, height = self._adb.screen_size()
        cx, cy = width // 2, height // 2
        dx, dy = int(width * 0.3), int(height * 0.3)
        # Swiping "up" scrolls content up (finger moves from lower to upper).
        vectors = {
            "up": (cx, cy + dy, cx, cy - dy),
            "down": (cx, cy - dy, cx, cy + dy),
            "left": (cx + dx, cy, cx - dx, cy),
            "right": (cx - dx, cy, cx + dx, cy),
        }
        if direction not in vectors:
            raise AIError(f"Unknown swipe direction: {direction!r}")
        x1, y1, x2, y2 = vectors[direction]
        self._adb.swipe(x1, y1, x2, y2)
        return f"swiped {direction}"


class Agent:
    """Drives a device toward a goal using a local LLM."""

    def __init__(
        self,
        adb: Adb,
        client: OllamaClient,
        *,
        max_steps: int = 15,
        sleep: Callable[[float], None] = time.sleep,
        settle_seconds: float = 1.0,
    ) -> None:
        self._adb = adb
        self._client = client
        self._executor = ActionExecutor(adb, sleep=sleep)
        self._max_steps = max_steps
        self._sleep = sleep
        self._settle = settle_seconds

    def run(
        self,
        goal: str,
        *,
        on_step: Callable[[AgentStep], None] | None = None,
    ) -> list[AgentStep]:
        """Pursue ``goal``, returning the list of steps taken.

        Args:
            goal: Natural-language objective.
            on_step: Optional callback invoked after each step (for live UI).
        """
        history: list[str] = []
        steps: list[AgentStep] = []
        for step_index in range(1, self._max_steps + 1):
            root = parse_hierarchy(self._adb.dump_ui())
            nodes = interactable_nodes(root)
            screen = summarize(root)
            prompt = build_user_prompt(goal, screen, history, step_index, self._max_steps)
            reply = self._client.chat(SYSTEM_PROMPT, prompt)
            action = parse_action(reply)

            if action.type is ActionType.DONE:
                detail = self._executor.execute(action, nodes)
                step = AgentStep(index=step_index, action=action, detail=detail)
                steps.append(step)
                if on_step:
                    on_step(step)
                return steps

            detail = self._executor.execute(action, nodes)
            step = AgentStep(index=step_index, action=action, detail=detail)
            steps.append(step)
            history.append(f"{action.type.value}: {detail}")
            if on_step:
                on_step(step)
            self._sleep(self._settle)

        raise AIError(f"Goal not reached within {self._max_steps} steps")
