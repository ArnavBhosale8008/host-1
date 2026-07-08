from __future__ import annotations

from droidpilot.gui.screen_view import map_click_to_device


def test_map_click_center():
    # Widget 400x800, pixmap fills it exactly, device 1080x2160.
    assert map_click_to_device((200, 400), (400, 800), (1080, 2160), (400, 800)) == (540, 1080)


def test_map_click_letterboxed():
    # Pixmap 200x800 centered in a 400x800 widget => 100px horizontal bars.
    result = map_click_to_device((150, 400), (400, 800), (1000, 4000), (200, 800))
    assert result == (250, 2000)


def test_map_click_outside_image_returns_none():
    # Click at x=10 lands in the left letterbox bar (bar is 100px wide).
    assert map_click_to_device((10, 400), (400, 800), (1000, 4000), (200, 800)) is None


def test_map_click_zero_pixmap_returns_none():
    assert map_click_to_device((10, 10), (400, 800), (1080, 2160), (0, 0)) is None
