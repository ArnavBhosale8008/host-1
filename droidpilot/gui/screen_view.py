"""Live device screen widget and background frame poller."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QThread, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

from ..core.adb import Adb


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
    """Displays the device screen and forwards taps back to the device."""

    tapped = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 400)
        self.setText("No device connected")
        self._device_size: tuple[int, int] = (1080, 1920)
        self._pixmap_size: tuple[int, int] = (0, 0)

    def set_device_size(self, width: int, height: int) -> None:
        self._device_size = (width, height)

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

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos: QPoint = event.position().toPoint()
        mapped = map_click_to_device(
            (pos.x(), pos.y()),
            (self.width(), self.height()),
            self._device_size,
            self._pixmap_size,
        )
        if mapped is not None:
            self.tapped.emit(*mapped)
