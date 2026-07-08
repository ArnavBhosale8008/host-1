from __future__ import annotations

from droidpilot.core.uihierarchy import (
    interactable_nodes,
    parse_bounds,
    parse_hierarchy,
    summarize,
)

SAMPLE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" bounds="[0,0][1080,1920]" enabled="true">
    <node text="Settings" resource-id="com.x:id/title" class="android.widget.TextView"
          clickable="false" enabled="true" bounds="[40,100][400,180]"/>
    <node text="" content-desc="Search" resource-id="com.x:id/search"
          class="android.widget.Button" clickable="true" enabled="true"
          bounds="[900,100][1000,200]"/>
    <node text="Hidden" clickable="true" enabled="true" bounds="[0,0][0,0]"/>
  </node>
</hierarchy>
"""


def test_parse_bounds_ok():
    b = parse_bounds("[10,20][110,220]")
    assert (b.left, b.top, b.right, b.bottom) == (10, 20, 110, 220)
    assert b.center == (60, 120)
    assert b.width == 100 and b.height == 200


def test_parse_bounds_malformed():
    assert parse_bounds("garbage") is None


def test_parse_hierarchy_and_walk():
    root = parse_hierarchy(SAMPLE)
    texts = [n.text for n in root.walk() if n.text]
    assert "Settings" in texts


def test_interactable_excludes_zero_area():
    root = parse_hierarchy(SAMPLE)
    nodes = interactable_nodes(root)
    labels = [n.label for n in nodes]
    assert "Settings" in labels
    assert "Search" in labels
    assert "Hidden" not in labels  # zero-area node filtered out


def test_summarize_format():
    root = parse_hierarchy(SAMPLE)
    text = summarize(root)
    assert "[0]" in text
    assert "(950,150)" in text  # center of the Search button
    assert "button" in text


def test_summarize_empty():
    root = parse_hierarchy("<hierarchy/>")
    assert summarize(root) == "<no interactable elements detected>"
