"""Parse ``uiautomator`` XML dumps into a compact, queryable element tree.

The AI agent uses this to reason about the screen without needing computer
vision: each node carries its text, resource id, description, and on-screen
bounds so the agent can decide where to tap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned bounding box in device pixels."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)


def parse_bounds(value: str) -> Bounds | None:
    """Parse a ``[l,t][r,b]`` bounds attribute, or ``None`` if malformed."""
    match = _BOUNDS_RE.search(value or "")
    if not match:
        return None
    left, top, right, bottom = (int(g) for g in match.groups())
    return Bounds(left=left, top=top, right=right, bottom=bottom)


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


@dataclass
class UiNode:
    """A single node in the UI hierarchy."""

    text: str = ""
    resource_id: str = ""
    content_desc: str = ""
    cls: str = ""
    package: str = ""
    clickable: bool = False
    enabled: bool = True
    bounds: Bounds | None = None
    children: list[UiNode] = field(default_factory=list)

    @property
    def label(self) -> str:
        """A human-readable label preferring text, then description, then id."""
        return self.text or self.content_desc or self.resource_id.split("/")[-1]

    def walk(self):
        """Yield this node and all descendants (pre-order)."""
        yield self
        for child in self.children:
            yield from child.walk()


def _node_from_element(el: ET.Element) -> UiNode:
    node = UiNode(
        text=el.get("text", ""),
        resource_id=el.get("resource-id", ""),
        content_desc=el.get("content-desc", ""),
        cls=el.get("class", ""),
        package=el.get("package", ""),
        clickable=_as_bool(el.get("clickable")),
        enabled=_as_bool(el.get("enabled")) or el.get("enabled") is None,
        bounds=parse_bounds(el.get("bounds", "")),
    )
    for child_el in list(el):
        node.children.append(_node_from_element(child_el))
    return node


def parse_hierarchy(xml: str) -> UiNode:
    """Parse a uiautomator XML string into a root :class:`UiNode`.

    The synthetic root wraps the top-level ``<hierarchy>`` element so callers
    always get a single node to :meth:`~UiNode.walk`.
    """
    root_el = ET.fromstring(xml)
    root = UiNode(cls=root_el.tag)
    for child_el in list(root_el):
        root.children.append(_node_from_element(child_el))
    return root


def interactable_nodes(root: UiNode) -> list[UiNode]:
    """Return enabled, on-screen nodes that are clickable or carry a label."""
    result: list[UiNode] = []
    for node in root.walk():
        if node.bounds is None or node.bounds.area <= 0 or not node.enabled:
            continue
        if node.clickable or node.label:
            result.append(node)
    return result


def summarize(root: UiNode, *, limit: int = 40) -> str:
    """Produce a compact, LLM-friendly listing of interactable elements.

    Each line is ``[index] <kind> "label" (cx,cy)`` where ``(cx,cy)`` is the tap
    point. The index lets the model refer to an element unambiguously.
    """
    lines: list[str] = []
    for index, node in enumerate(interactable_nodes(root)[:limit]):
        assert node.bounds is not None  # guaranteed by interactable_nodes
        cx, cy = node.bounds.center
        kind = "button" if node.clickable else "text"
        label = node.label.replace("\n", " ").strip()[:60] or "<no label>"
        lines.append(f'[{index}] {kind} "{label}" ({cx},{cy})')
    return "\n".join(lines) if lines else "<no interactable elements detected>"
