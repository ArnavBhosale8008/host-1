"""Keyboard/mouse -> touch key-mapping for gaming.

A :class:`KeyMap` is a resolution-independent description of how physical keys
map onto the device screen:

* :class:`TapBinding` — a key that taps a fixed point (fire, jump, reload...).
* :class:`SwipeBinding` — a key that swipes between two points.
* :class:`Joystick` — four keys (typically WASD) that drive a virtual analog
  stick via continuous touch (``motionevent`` DOWN/MOVE/UP).

Coordinates are stored **normalized** to ``0.0..1.0`` of the screen so a map
authored on one device size still works on another. All of the geometry lives
in small pure functions (:func:`resolve_point`, :func:`joystick_target`) so it
can be unit tested without a device.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class TapBinding:
    """A key that taps a single normalized point."""

    key: str
    x: float
    y: float
    label: str = ""


@dataclass(frozen=True)
class SwipeBinding:
    """A key that swipes from ``(x, y)`` to ``(x2, y2)``."""

    key: str
    x: float
    y: float
    x2: float
    y2: float
    duration_ms: int = 150
    label: str = ""


@dataclass(frozen=True)
class Joystick:
    """A WASD-style analog stick centered at ``(x, y)``.

    ``radius`` is a fraction of the smaller screen dimension; a fully-deflected
    direction moves the touch point that far from the center.
    """

    up: str
    down: str
    left: str
    right: str
    x: float
    y: float
    radius: float = 0.12

    @property
    def keys(self) -> frozenset[str]:
        return frozenset({self.up, self.down, self.left, self.right})


@dataclass
class KeyMap:
    """A named collection of bindings."""

    name: str = "default"
    taps: list[TapBinding] = field(default_factory=list)
    swipes: list[SwipeBinding] = field(default_factory=list)
    joystick: Joystick | None = None

    def to_json(self) -> str:
        data = {
            "name": self.name,
            "taps": [asdict(t) for t in self.taps],
            "swipes": [asdict(s) for s in self.swipes],
            "joystick": asdict(self.joystick) if self.joystick else None,
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, text: str) -> KeyMap:
        data = json.loads(text)
        joystick_data = data.get("joystick")
        return cls(
            name=str(data.get("name", "default")),
            taps=[TapBinding(**t) for t in data.get("taps", [])],
            swipes=[SwipeBinding(**s) for s in data.get("swipes", [])],
            joystick=Joystick(**joystick_data) if joystick_data else None,
        )


def default_keymap() -> KeyMap:
    """A sensible starting map: WASD stick + common action buttons.

    Points are placed for a portrait shooter-style layout (stick bottom-left,
    fire/jump bottom-right). Users are expected to tweak these to their game.
    """
    return KeyMap(
        name="default",
        taps=[
            TapBinding(key="J", x=0.85, y=0.80, label="Fire"),
            TapBinding(key="SPACE", x=0.90, y=0.62, label="Jump"),
            TapBinding(key="R", x=0.72, y=0.80, label="Reload"),
            TapBinding(key="F", x=0.80, y=0.50, label="Action"),
        ],
        swipes=[],
        joystick=Joystick(up="W", down="S", left="A", right="D", x=0.22, y=0.75, radius=0.14),
    )


def default_keymap_path() -> Path:
    """Where the user's key map is persisted, per platform."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "DroidPilot" / "keymap.json"
    return Path.home() / ".config" / "droidpilot" / "keymap.json"


def load_keymap(path: Path) -> KeyMap:
    """Load a key map from ``path``, falling back to :func:`default_keymap`."""
    if path.exists():
        return KeyMap.from_json(path.read_text(encoding="utf-8"))
    return default_keymap()


def save_keymap(keymap: KeyMap, path: Path) -> None:
    """Persist ``keymap`` to ``path``, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(keymap.to_json(), encoding="utf-8")


def resolve_point(x: float, y: float, size: tuple[int, int]) -> tuple[int, int]:
    """Convert a normalized point to integer device pixels, clamped to screen."""
    width, height = size
    px = min(max(int(round(x * width)), 0), max(width - 1, 0))
    py = min(max(int(round(y * height)), 0), max(height - 1, 0))
    return px, py


def joystick_target(
    joystick: Joystick,
    pressed: set[str],
    size: tuple[int, int],
) -> tuple[int, int]:
    """Return the device-pixel touch point for the currently pressed directions.

    The four direction keys sum into a vector which is normalized to unit
    length (so diagonals don't travel farther than cardinals) and scaled by the
    joystick radius. With nothing pressed the point is the center.
    """
    width, height = size
    dx = (1 if joystick.right in pressed else 0) - (1 if joystick.left in pressed else 0)
    dy = (1 if joystick.down in pressed else 0) - (1 if joystick.up in pressed else 0)
    cx, cy = joystick.x * width, joystick.y * height
    if dx == 0 and dy == 0:
        return int(round(cx)), int(round(cy))
    length = math.hypot(dx, dy)
    radius_px = joystick.radius * min(width, height)
    tx = cx + (dx / length) * radius_px
    ty = cy + (dy / length) * radius_px
    px = min(max(int(round(tx)), 0), max(width - 1, 0))
    py = min(max(int(round(ty)), 0), max(height - 1, 0))
    return px, py


class InputSink(Protocol):
    """The subset of :class:`~droidpilot.core.adb.Adb` a mapper needs."""

    def tap(self, x: int, y: int) -> None: ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = ...) -> None: ...

    def motion_event(self, action: str, x: int, y: int) -> None: ...


class KeyMapper:
    """Translates key press/release events into device touch input.

    Taps and swipes fire on key *press*. The joystick holds a single touch
    (``DOWN``) that follows the pressed direction keys (``MOVE``) and lifts
    (``UP``) once all directions are released.
    """

    def __init__(self, sink: InputSink, keymap: KeyMap, size: tuple[int, int]) -> None:
        self._sink = sink
        self._keymap = keymap
        self._size = size
        self._tap_by_key = {t.key: t for t in keymap.taps}
        self._swipe_by_key = {s.key: s for s in keymap.swipes}
        self._joystick = keymap.joystick
        self._pressed_dirs: set[str] = set()
        self._pointer_down = False

    def handles(self, key: str) -> bool:
        """Return whether ``key`` is bound in this map."""
        if key in self._tap_by_key or key in self._swipe_by_key:
            return True
        return self._joystick is not None and key in self._joystick.keys

    def press(self, key: str) -> None:
        if self._joystick is not None and key in self._joystick.keys:
            self._pressed_dirs.add(key)
            self._update_joystick()
            return
        tap = self._tap_by_key.get(key)
        if tap is not None:
            x, y = resolve_point(tap.x, tap.y, self._size)
            self._sink.tap(x, y)
            return
        swipe = self._swipe_by_key.get(key)
        if swipe is not None:
            x1, y1 = resolve_point(swipe.x, swipe.y, self._size)
            x2, y2 = resolve_point(swipe.x2, swipe.y2, self._size)
            self._sink.swipe(x1, y1, x2, y2, swipe.duration_ms)

    def release(self, key: str) -> None:
        if self._joystick is not None and key in self._joystick.keys:
            self._pressed_dirs.discard(key)
            self._update_joystick()

    def reset(self) -> None:
        """Lift any held joystick touch and forget pressed directions."""
        if self._pointer_down and self._joystick is not None:
            cx, cy = resolve_point(self._joystick.x, self._joystick.y, self._size)
            self._sink.motion_event("UP", cx, cy)
        self._pointer_down = False
        self._pressed_dirs.clear()

    def _update_joystick(self) -> None:
        if self._joystick is None:
            return
        tx, ty = joystick_target(self._joystick, self._pressed_dirs, self._size)
        if self._pressed_dirs:
            action = "MOVE" if self._pointer_down else "DOWN"
            self._sink.motion_event(action, tx, ty)
            self._pointer_down = True
        elif self._pointer_down:
            self._sink.motion_event("UP", tx, ty)
            self._pointer_down = False
