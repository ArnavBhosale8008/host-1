from __future__ import annotations

from droidpilot.core.keymap import (
    Joystick,
    KeyMap,
    KeyMapper,
    SwipeBinding,
    TapBinding,
    default_keymap,
    joystick_target,
    load_keymap,
    resolve_point,
    save_keymap,
)

SIZE = (1000, 2000)


class RecordingSink:
    """Captures the input calls a KeyMapper makes."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.calls.append(("swipe", x1, y1, x2, y2, duration_ms))

    def motion_event(self, action: str, x: int, y: int) -> None:
        self.calls.append(("motion", action, x, y))


def test_resolve_point_scales_and_clamps():
    assert resolve_point(0.5, 0.5, SIZE) == (500, 1000)
    assert resolve_point(0.0, 0.0, SIZE) == (0, 0)
    assert resolve_point(1.5, 1.5, SIZE) == (999, 1999)


def test_joystick_target_center_when_nothing_pressed():
    js = Joystick(up="W", down="S", left="A", right="D", x=0.2, y=0.75, radius=0.1)
    assert joystick_target(js, set(), SIZE) == (200, 1500)


def test_joystick_target_cardinal_uses_full_radius():
    js = Joystick(up="W", down="S", left="A", right="D", x=0.5, y=0.5, radius=0.1)
    # radius_px = 0.1 * min(1000,2000) = 100; pressing D moves +100 in x.
    assert joystick_target(js, {"D"}, SIZE) == (600, 1000)
    assert joystick_target(js, {"W"}, SIZE) == (500, 900)


def test_joystick_target_diagonal_is_normalized():
    js = Joystick(up="W", down="S", left="A", right="D", x=0.5, y=0.5, radius=0.1)
    # Diagonal: each axis gets 100/sqrt(2) ~= 70.7 -> rounds to 71.
    assert joystick_target(js, {"D", "S"}, SIZE) == (571, 1071)


def test_mapper_tap_and_swipe_fire_on_press():
    km = KeyMap(
        taps=[TapBinding(key="J", x=0.9, y=0.8)],
        swipes=[SwipeBinding(key="K", x=0.1, y=0.1, x2=0.2, y2=0.2, duration_ms=120)],
    )
    sink = RecordingSink()
    mapper = KeyMapper(sink, km, SIZE)
    mapper.press("J")
    mapper.press("K")
    assert sink.calls == [
        ("tap", 900, 1600),
        ("swipe", 100, 200, 200, 400, 120),
    ]


def test_mapper_joystick_down_move_up_lifecycle():
    js = Joystick(up="W", down="S", left="A", right="D", x=0.5, y=0.5, radius=0.1)
    sink = RecordingSink()
    mapper = KeyMapper(sink, KeyMap(joystick=js), SIZE)

    mapper.press("D")  # first direction -> DOWN
    mapper.press("W")  # second direction -> MOVE to diagonal
    mapper.release("D")  # still holding W -> MOVE
    mapper.release("W")  # nothing pressed -> UP

    actions = [c[1] for c in sink.calls]
    assert actions == ["DOWN", "MOVE", "MOVE", "UP"]
    # First DOWN is at the +x cardinal; final UP lifts wherever it ended.
    assert sink.calls[0] == ("motion", "DOWN", 600, 1000)
    assert sink.calls[-1][1] == "UP"


def test_mapper_reset_lifts_held_pointer():
    js = Joystick(up="W", down="S", left="A", right="D", x=0.5, y=0.5, radius=0.1)
    sink = RecordingSink()
    mapper = KeyMapper(sink, KeyMap(joystick=js), SIZE)
    mapper.press("W")
    sink.calls.clear()
    mapper.reset()
    assert sink.calls == [("motion", "UP", 500, 1000)]


def test_mapper_handles_reports_bound_keys():
    mapper = KeyMapper(RecordingSink(), default_keymap(), SIZE)
    assert mapper.handles("W") and mapper.handles("J")
    assert not mapper.handles("Z")


def test_keymap_json_roundtrip():
    km = default_keymap()
    restored = KeyMap.from_json(km.to_json())
    assert restored.name == km.name
    assert restored.taps == km.taps
    assert restored.joystick == km.joystick


def test_load_keymap_falls_back_to_default_when_missing(tmp_path):
    km = load_keymap(tmp_path / "nope.json")
    assert km.joystick is not None


def test_save_then_load_keymap_roundtrips(tmp_path):
    path = tmp_path / "nested" / "keymap.json"
    original = KeyMap(name="custom", taps=[TapBinding(key="J", x=0.5, y=0.5)])
    save_keymap(original, path)
    assert path.exists()
    loaded = load_keymap(path)
    assert loaded.name == "custom"
    assert loaded.taps == original.taps
