"""Live device screen widget and background frame poller."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QThread, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QLabel, QSizePolicy

from ..core.adb import Adb
from ..core.keymap import KeyMap

_SPECIAL_KEYS = {
    Qt.Key.Key_Space: "SPACE",
    Qt.Key.Key_Up: "UP",
    Qt.Key.Key_Down: "DOWN",
    Qt.Key.Key_Left: "LEFT",
    Qt.Key.Key_Right: "RIGHT",
    Qt.Key.Key_Shift: "SHIFT",
    Qt.Key.Key_Control: "CTRL",
    Qt.Key.Key_Return: "ENTER",
    Qt.Key.Key_Enter: "ENTER",
}


def key_name_from_event(event: QKeyEvent) -> str | None:
    """Return a normalized key name (e.g. ``"W"``, ``"SPACE"``) or ``None``."""
    special = _SPECIAL_KEYS.get(Qt.Key(event.key()))
    if special is not None:
        return special
    text = event.text().upper().strip()
    if len(text) == 1 and text.isalnum():
        return text
    return None


class ScreenPoller(QThread):
    """Polls the device for screenshots on a background thread.

    Emits :attr:`frame` with raw PNG bytes and :attr:`error` with a message.
    """

    frame = Signal(bytes)
    error = Signal(str)

    def __init__(self, adb: Adb, interval_ms: int = 500, parent=None) -> None:
        super().__init__(parent)
        self._adb = adb
        self._interval_ms = interval_ms
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:  # pragma: no cover - requires a live device
        self._running = True
        while self._running:
            try:
                png = self._adb.screencap_png()
                self.frame.emit(png)
            except Exception as exc:  # noqa: BLE001 - reported to the UI
                self.error.emit(str(exc))
            self.msleep(self._interval_ms)


def map_click_to_device(
    click: tuple[int, int],
    widget_size: tuple[int, int],
    device_size: tuple[int, int],
    pixmap_size: tuple[int, int],
) -> tuple[int, int] | None:
    """Map a click within the widget to device pixel coordinates.

    The pixmap is centered inside the widget (letter-boxed). Returns ``None`` if
    the click lands outside the rendered image.

    Args:
        click: ``(x, y)`` click position in widget coordinates.
        widget_size: ``(w, h)`` of the widget.
        device_size: ``(w, h)`` of the real device screen.
        pixmap_size: ``(w, h)`` the image is actually drawn at.
    """
    click_x, click_y = click
    widget_w, widget_h = widget_size
    pix_w, pix_h = pixmap_size
    if pix_w <= 0 or pix_h <= 0:
        return None
    offset_x = (widget_w - pix_w) / 2
    offset_y = (widget_h - pix_h) / 2
    local_x = click_x - offset_x
    local_y = click_y - offset_y
    if not (0 <= local_x <= pix_w and 0 <= local_y <= pix_h):
        return None
    dev_w, dev_h = device_size
    return (
        int(local_x / pix_w * dev_w),
        int(local_y / pix_h * dev_h),
    )


class ScreenView(QLabel):
    """Displays the device screen and forwards taps/keys back to the device."""

    tapped = Signal(int, int)
    key_pressed = Signal(str)
    key_released = Signal(str)
    # Emitted with a normalized (x, y) in 0..1 when a spot is clicked in edit mode.
    point_placed = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 400)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setText("No device connected")
        self._device_size: tuple[int, int] = (1080, 1920)
        self._pixmap_size: tuple[int, int] = (0, 0)
        self._keymapping = False
        self._edit_mode = False
        self._overlay: KeyMap | None = None

    def set_device_size(self, width: int, height: int) -> None:
        self._device_size = (width, height)

    def set_keymapping(self, enabled: bool, keymap: KeyMap | None = None) -> None:
        """Enable/disable key capture and show the binding overlay."""
        self._keymapping = enabled
        self._overlay = keymap if enabled else None
        if enabled:
            self.setFocus()
        self.update()

    def set_edit_mode(self, enabled: bool, keymap: KeyMap | None = None) -> None:
        """When enabled, clicks emit :attr:`point_placed` instead of tapping."""
        self._edit_mode = enabled
        if keymap is not None:
            self._overlay = keymap
        self.update()

    def clear_device(self) -> None:
        """Reset to the 'no device' placeholder."""
        self._pixmap_size = (0, 0)
        self.setPixmap(QPixmap())
        self.setText("No device connected")

    def update_frame(self, png: bytes) -> None:
        """Render a new PNG frame, scaled to fit while preserving aspect."""
        image = QImage.fromData(png, "PNG")
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._pixmap_size = (scaled.width(), scaled.height())
        self.setPixmap(scaled)
        if self._overlay is not None:
            self.update()

    def _pixmap_offset(self) -> tuple[float, float]:
        pix_w, pix_h = self._pixmap_size
        return (self.width() - pix_w) / 2, (self.height() - pix_h) / 2

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos: QPoint = event.position().toPoint()
        if self._edit_mode:
            pix_w, pix_h = self._pixmap_size
            if pix_w <= 0 or pix_h <= 0:
                return
            off_x, off_y = self._pixmap_offset()
            nx = (pos.x() - off_x) / pix_w
            ny = (pos.y() - off_y) / pix_h
            if 0 <= nx <= 1 and 0 <= ny <= 1:
                self.point_placed.emit(nx, ny)
            return
        mapped = map_click_to_device(
            (pos.x(), pos.y()),
            (self.width(), self.height()),
            self._device_size,
            self._pixmap_size,
        )
        if mapped is not None:
            self.tapped.emit(*mapped)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if self._keymapping and not event.isAutoRepeat():
            name = key_name_from_event(event)
            if name is not None:
                self.key_pressed.emit(name)
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if self._keymapping and not event.isAutoRepeat():
            name = key_name_from_event(event)
            if name is not None:
                self.key_released.emit(name)
                return
        super().keyReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        overlay = self._overlay
        pix_w, pix_h = self._pixmap_size
        if overlay is None or pix_w <= 0 or pix_h <= 0:
            return
        off_x, off_y = self._pixmap_offset()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont()
        font.setBold(True)
        painter.setFont(font)

        def draw_badge(nx: float, ny: float, text: str, color: QColor) -> None:
            cx = off_x + nx * pix_w
            cy = off_y + ny * pix_h
            radius = 18
            painter.setBrush(color)
            painter.setPen(QColor(255, 255, 255))
            painter.drawEllipse(QPoint(int(cx), int(cy)), radius, radius)
            painter.drawText(
                int(cx - radius),
                int(cy - radius),
                radius * 2,
                radius * 2,
                Qt.AlignmentFlag.AlignCenter,
                text,
            )

        blue = QColor(30, 120, 220, 200)
        green = QColor(40, 160, 90, 200)
        for tap in overlay.taps:
            draw_badge(tap.x, tap.y, tap.key, blue)
        for swipe in overlay.swipes:
            draw_badge(swipe.x, swipe.y, swipe.key, blue)
        if overlay.joystick is not None:
            js = overlay.joystick
            cx = off_x + js.x * pix_w
            cy = off_y + js.y * pix_h
            ring = js.radius * min(pix_w, pix_h)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(40, 160, 90, 220))
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(ring), int(ring))
            draw_badge(js.x, js.y, "WASD", green)
        painter.end()
