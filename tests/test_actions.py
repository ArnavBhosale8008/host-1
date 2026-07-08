from __future__ import annotations

import pytest

from droidpilot.ai.actions import Action, ActionType, parse_action
from droidpilot.core.errors import AIError


def test_parse_nested_action():
    action = parse_action('{"thought": "tap it", "action": {"type": "tap", "x": 5, "y": 6}}')
    assert action.type is ActionType.TAP
    assert action.thought == "tap it"
    assert action.params == {"x": 5, "y": 6}


def test_parse_tap_element():
    action = parse_action('{"action": {"type": "tap_element", "index": 3}}')
    assert action.type is ActionType.TAP_ELEMENT
    assert action.params["index"] == 3


def test_parse_from_code_fence():
    text = "Sure!\n```json\n{\"action\": {\"type\": \"done\", \"success\": true}}\n```"
    action = parse_action(text)
    assert action.type is ActionType.DONE


def test_parse_string_action_form():
    action = parse_action('{"action": "wait", "seconds": 2}')
    assert action.type is ActionType.WAIT
    assert action.params == {"seconds": 2}


def test_parse_done_with_surrounding_prose():
    action = parse_action('The task is complete. {"action": {"type": "done"}} Thanks!')
    assert action.type is ActionType.DONE


def test_parse_unknown_action_raises():
    with pytest.raises(AIError):
        parse_action('{"action": {"type": "explode"}}')


def test_parse_no_json_raises():
    with pytest.raises(AIError):
        parse_action("I cannot help with that")


def test_parse_invalid_json_raises():
    with pytest.raises(AIError):
        parse_action('{"action": {"type": "tap", }}')


def test_action_default_params():
    assert Action(type=ActionType.DONE).params == {}
