from __future__ import annotations

from pathlib import Path

import pytest

from droidpilot.ai.actions import Action, ActionType, parse_action
from droidpilot.ai.agent import ActionExecutor, Agent
from droidpilot.core.adb import Adb
from droidpilot.core.errors import AIError
from droidpilot.core.process import CommandResult
from droidpilot.core.uihierarchy import interactable_nodes, parse_hierarchy

from .fakes import FakeRunner

ADB = Path("/sdk/platform-tools/adb")

UI_XML = """<?xml version='1.0'?>
<hierarchy>
  <node text="Settings" clickable="true" enabled="true" bounds="[0,0][200,100]"/>
  <node text="Wi-Fi" clickable="true" enabled="true" bounds="[0,100][200,200]"/>
</hierarchy>
"""


def _device_runner() -> FakeRunner:
    def handler(args):
        if "cat" in args:
            return CommandResult(returncode=0, stdout=UI_XML)
        if "dump" in args:
            return CommandResult(returncode=0, stdout="dumped to: /sdcard/x")
        if "size" in args:
            return CommandResult(returncode=0, stdout="Physical size: 400x800")
        return CommandResult(returncode=0, stdout="")

    return FakeRunner(handler)


class ScriptedClient:
    """A stand-in for OllamaClient that returns queued replies."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def chat(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self._replies.pop(0)


def test_executor_tap_element():
    runner = _device_runner()
    adb = Adb(ADB, runner=runner)
    nodes = interactable_nodes(parse_hierarchy(UI_XML))
    executor = ActionExecutor(adb, sleep=lambda s: None)
    detail = executor.execute(parse_action('{"action":{"type":"tap_element","index":1}}'), nodes)
    assert "Wi-Fi" in detail
    assert runner.calls[-1][-2:] == ["100", "150"]  # center of node 1


def test_executor_tap_element_out_of_range():
    adb = Adb(ADB, runner=_device_runner())
    nodes = interactable_nodes(parse_hierarchy(UI_XML))
    executor = ActionExecutor(adb, sleep=lambda s: None)
    with pytest.raises(AIError):
        executor.execute(Action(type=ActionType.TAP_ELEMENT, params={"index": 9}), nodes)


def test_executor_swipe_direction():
    runner = _device_runner()
    adb = Adb(ADB, runner=runner)
    executor = ActionExecutor(adb, sleep=lambda s: None)
    detail = executor.execute(Action(type=ActionType.SWIPE, params={"direction": "up"}), [])
    assert detail == "swiped up"
    assert runner.calls[-1][3] == "swipe"


def test_executor_unknown_key():
    adb = Adb(ADB, runner=_device_runner())
    executor = ActionExecutor(adb, sleep=lambda s: None)
    with pytest.raises(AIError):
        executor.execute(Action(type=ActionType.KEY, params={"name": "power"}), [])


def test_agent_runs_until_done():
    runner = _device_runner()
    adb = Adb(ADB, runner=runner)
    client = ScriptedClient(
        [
            '{"thought":"open wifi","action":{"type":"tap_element","index":1}}',
            '{"thought":"finished","action":{"type":"done","summary":"opened wifi"}}',
        ]
    )
    agent = Agent(adb, client, max_steps=5, sleep=lambda s: None)
    steps = agent.run("open wifi")
    assert len(steps) == 2
    assert steps[-1].action.type is ActionType.DONE
    assert steps[-1].detail == "opened wifi"


def test_agent_reports_steps_via_callback():
    adb = Adb(ADB, runner=_device_runner())
    client = ScriptedClient(['{"action":{"type":"done","summary":"ok"}}'])
    agent = Agent(adb, client, sleep=lambda s: None)
    seen = []
    agent.run("noop", on_step=seen.append)
    assert len(seen) == 1


def test_agent_raises_when_max_steps_exceeded():
    adb = Adb(ADB, runner=_device_runner())
    client = ScriptedClient(['{"action":{"type":"swipe","direction":"up"}}'] * 10)
    agent = Agent(adb, client, max_steps=2, sleep=lambda s: None)
    with pytest.raises(AIError):
        agent.run("scroll forever")
