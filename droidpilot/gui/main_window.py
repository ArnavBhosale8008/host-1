"""The DroidPilot main window."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ai.agent import Agent, AgentStep
from ..ai.ollama_client import OllamaClient
from ..config import Config
from ..core.adb import Adb
from ..core.emulator import (
    GAME_MODE_CORES,
    GAME_MODE_GPU,
    GAME_MODE_MEMORY_MB,
    EmulatorController,
    EmulatorSession,
)
from ..core.errors import DroidPilotError
from ..core.keymap import (
    Joystick,
    KeyMap,
    KeyMapper,
    TapBinding,
    default_keymap,
    default_keymap_path,
    load_keymap,
    save_keymap,
)
from ..core.sdk import Sdk, locate_sdk
from .screen_view import ScreenPoller, ScreenView


class AgentWorker(QThread):
    """Runs an :class:`Agent` goal off the UI thread."""

    step = Signal(object)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, agent: Agent, goal: str, parent=None) -> None:
        super().__init__(parent)
        self._agent = agent
        self._goal = goal

    def run(self) -> None:  # pragma: no cover - requires device + model
        try:
            steps = self._agent.run(self._goal, on_step=self.step.emit)
            self.finished_ok.emit(steps)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QWidget):
    """Top-level window wiring the device controls, screen, and AI panel."""

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self._config = config or Config.from_env()
        self._sdk: Sdk | None = None
        self._controller: EmulatorController | None = None
        self._session: EmulatorSession | None = None
        self._adb: Adb | None = None
        self._poller: ScreenPoller | None = None
        self._agent_worker: AgentWorker | None = None
        self._booted = False
        self._keymap_path = default_keymap_path()
        self._keymap = load_keymap(self._keymap_path)
        self._mapper: KeyMapper | None = None
        self._mapper_size: tuple[int, int] | None = None
        self._device_size: tuple[int, int] = (1080, 1920)

        self.setWindowTitle("DroidPilot")
        self.resize(1000, 720)
        self._build_ui()
        self._init_sdk()

    # -- UI construction -----------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        self.screen = ScreenView()
        self.screen.tapped.connect(self._on_screen_tap)
        self.screen.key_pressed.connect(self._on_key_pressed)
        self.screen.key_released.connect(self._on_key_released)
        self.screen.point_placed.connect(self._on_point_placed)
        root.addWidget(self.screen, stretch=3)

        side = QVBoxLayout()
        root.addLayout(side, stretch=2)

        side.addWidget(self._build_device_group())
        side.addWidget(self._build_game_group())
        side.addWidget(self._build_app_group())
        side.addWidget(self._build_ai_group(), stretch=1)

        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        side.addWidget(self.status)

    def _build_device_group(self) -> QGroupBox:
        box = QGroupBox("Virtual device")
        layout = QVBoxLayout(box)
        self.avd_combo = QComboBox()
        layout.addWidget(self.avd_combo)
        buttons = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.stop_btn)
        layout.addLayout(buttons)
        self.show_window_chk = QCheckBox("Show native emulator window (better for games)")
        layout.addWidget(self.show_window_chk)
        return box

    def _build_game_group(self) -> QGroupBox:
        box = QGroupBox("Game controls")
        layout = QVBoxLayout(box)
        self.game_mode_chk = QCheckBox("Optimize for games (GPU + more RAM)")
        layout.addWidget(self.game_mode_chk)
        self.keymap_chk = QCheckBox("Enable key mapping (keyboard \u2192 touch)")
        self.keymap_chk.toggled.connect(self._on_keymap_toggled)
        layout.addWidget(self.keymap_chk)
        row = QHBoxLayout()
        self.edit_keys_btn = QPushButton("Edit keys")
        self.edit_keys_btn.setCheckable(True)
        self.edit_keys_btn.toggled.connect(self._on_edit_keys_toggled)
        row.addWidget(self.edit_keys_btn)
        self.place_combo = QComboBox()
        self.place_combo.addItems(["Button", "Move stick (WASD)"])
        row.addWidget(self.place_combo)
        layout.addLayout(row)
        row2 = QHBoxLayout()
        for label, handler in (
            ("Save\u2026", self._on_save_keymap),
            ("Load\u2026", self._on_load_keymap),
            ("Reset", self._on_reset_keymap),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            row2.addWidget(btn)
        layout.addLayout(row2)
        return box

    def _build_app_group(self) -> QGroupBox:
        box = QGroupBox("Apps & input")
        layout = QVBoxLayout(box)
        self.install_btn = QPushButton("Install APK…")
        self.install_btn.clicked.connect(self._on_install)
        layout.addWidget(self.install_btn)
        keys = QHBoxLayout()
        for label, handler in (
            ("Back", lambda: self._with_adb(lambda a: a.press_back())),
            ("Home", lambda: self._with_adb(lambda a: a.press_home())),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            keys.addWidget(btn)
        layout.addLayout(keys)
        return box

    def _build_ai_group(self) -> QGroupBox:
        box = QGroupBox("AI assistant (local)")
        layout = QVBoxLayout(box)
        prompt_row = QHBoxLayout()
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText("e.g. open Settings and turn on airplane mode")
        self.ai_input.returnPressed.connect(self._on_run_ai)
        self.ai_run_btn = QPushButton("Run")
        self.ai_run_btn.clicked.connect(self._on_run_ai)
        prompt_row.addWidget(self.ai_input)
        prompt_row.addWidget(self.ai_run_btn)
        layout.addLayout(prompt_row)
        self.ai_log = QPlainTextEdit()
        self.ai_log.setReadOnly(True)
        layout.addWidget(self.ai_log)
        return box

    # -- Initialization ------------------------------------------------------
    def _init_sdk(self) -> None:
        try:
            self._sdk = locate_sdk(self._config.sdk_root)
        except DroidPilotError as exc:
            self._set_status(f"SDK not found: {exc}")
            self.start_btn.setEnabled(False)
            return
        self._controller = EmulatorController(self._sdk)
        try:
            avds = self._controller.list_avds()
        except DroidPilotError as exc:
            self._set_status(f"Could not list AVDs: {exc}")
            avds = []
        self.avd_combo.addItems(avds)
        self._set_status(f"SDK: {self._sdk.root}")

    # -- Device lifecycle ----------------------------------------------------
    def _on_start(self) -> None:
        if self._controller is None:
            return
        avd = self.avd_combo.currentText()
        if not avd:
            self._set_status("No AVD selected")
            return
        headless = not self.show_window_chk.isChecked()
        gpu = memory = cores = None
        if self.game_mode_chk.isChecked():
            gpu, memory, cores = GAME_MODE_GPU, GAME_MODE_MEMORY_MB, GAME_MODE_CORES
        try:
            self._session = self._controller.start(
                avd, headless=headless, gpu=gpu, memory_mb=memory, cores=cores
            )
        except DroidPilotError as exc:
            self._show_error("Failed to start emulator", str(exc))
            return
        self._adb = Adb(self._sdk.adb)  # type: ignore[union-attr]
        self._booted = False
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_status(f"Starting {avd}… waiting for boot (this can take a minute)")
        self._start_polling()

    def _on_stop(self) -> None:
        self._stop_polling()
        if self._session is not None:
            self._session.stop()
            self._session = None
        self._adb = None
        self._booted = False
        self._mapper = None
        self._mapper_size = None
        self.screen.clear_device()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_status("Stopped")

    def _start_polling(self) -> None:
        if self._adb is None:
            return
        self._poller = ScreenPoller(self._adb, self._config.screen_refresh_ms)
        self._poller.frame.connect(self._on_frame)
        self._poller.error.connect(self._on_poll_error)
        self._poller.start()

    def _stop_polling(self) -> None:
        if self._poller is not None:
            self._poller.stop()
            self._poller.wait(2000)
            self._poller = None

    def _on_frame(self, png: bytes) -> None:
        if self._poller is None:
            # A frame queued before Stop; ignore so the view stays cleared.
            return
        try:
            if self._adb is not None:
                try:
                    size = self._adb.screen_size()
                    self.screen.set_device_size(*size)
                    if size != self._device_size:
                        self._device_size = size
                        self._mapper = None
                except DroidPilotError:
                    pass
            self.screen.update_frame(png)
        except Exception:  # noqa: BLE001 - never let a bad frame crash the UI
            return
        if not self._booted:
            self._booted = True
            self._set_status("Device connected")

    def _on_poll_error(self, message: str) -> None:
        if self._poller is None:
            return
        # Before boot, screencap failures/timeouts are expected; keep it calm.
        if not self._booted:
            self._set_status("Starting device… waiting for boot (this can take a minute)")
        else:
            self._set_status(message)

    # -- Interaction ---------------------------------------------------------
    def _on_screen_tap(self, x: int, y: int) -> None:
        self._with_adb(lambda a: a.tap(x, y))

    def _on_install(self) -> None:
        if self._adb is None:
            self._set_status("Start a device first")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select APK", "", "APK files (*.apk)")
        if not path:
            return
        try:
            self._adb.install(Path(path))
            self._set_status(f"Installed {path}")
        except DroidPilotError as exc:
            self._show_error("Install failed", str(exc))

    def _on_run_ai(self) -> None:
        if self._adb is None:
            self._set_status("Start a device first")
            return
        goal = self.ai_input.text().strip()
        if not goal:
            return
        client = OllamaClient(self._config.ollama_host, self._config.ollama_model)
        if not client.is_available():
            self._show_error(
                "Local AI unavailable",
                f"Ollama is not reachable at {self._config.ollama_host}. "
                "Install it from https://ollama.com and pull a model.",
            )
            return
        agent = Agent(self._adb, client)
        self.ai_log.appendPlainText(f"> {goal}")
        self.ai_run_btn.setEnabled(False)
        self._agent_worker = AgentWorker(agent, goal)
        self._agent_worker.step.connect(self._on_agent_step)
        self._agent_worker.finished_ok.connect(self._on_agent_done)
        self._agent_worker.failed.connect(self._on_agent_failed)
        self._agent_worker.start()

    def _on_agent_step(self, step: AgentStep) -> None:
        thought = f" — {step.action.thought}" if step.action.thought else ""
        self.ai_log.appendPlainText(f"  {step.index}. {step.detail}{thought}")

    def _on_agent_done(self, steps: list) -> None:
        self.ai_run_btn.setEnabled(True)
        self.ai_log.appendPlainText(f"  done ({len(steps)} steps)")

    def _on_agent_failed(self, message: str) -> None:
        self.ai_run_btn.setEnabled(True)
        self.ai_log.appendPlainText(f"  failed: {message}")

    # -- Key mapping ---------------------------------------------------------
    def _on_keymap_toggled(self, on: bool) -> None:
        self._mapper = None
        self.screen.set_keymapping(on, self._keymap if on else None)
        if on:
            self._set_status("Key mapping on \u2014 click the screen, then use your keys")
        else:
            self.edit_keys_btn.setChecked(False)

    def _on_edit_keys_toggled(self, on: bool) -> None:
        self.screen.set_edit_mode(on, self._keymap)
        if on:
            self._set_status("Edit mode: click where a key/stick should go")

    def _on_point_placed(self, nx: float, ny: float) -> None:
        if self.place_combo.currentIndex() == 1:
            if self._keymap.joystick is None:
                self._keymap.joystick = Joystick(
                    up="W", down="S", left="A", right="D", x=nx, y=ny
                )
            else:
                self._keymap.joystick = replace(self._keymap.joystick, x=nx, y=ny)
        else:
            key, ok = QInputDialog.getText(self, "Bind key", "Key name (e.g. J, SPACE):")
            key = key.strip().upper()
            if not ok or not key:
                return
            self._keymap.taps.append(TapBinding(key=key, x=nx, y=ny, label=key))
        self._persist_keymap()
        self._mapper = None
        self.screen.set_edit_mode(True, self._keymap)

    def _on_save_keymap(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save key map", "keymap.json", "JSON (*.json)")
        if not path:
            return
        try:
            save_keymap(self._keymap, Path(path))
            self._set_status(f"Saved key map to {path}")
        except OSError as exc:
            self._show_error("Could not save key map", str(exc))

    def _on_load_keymap(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load key map", "", "JSON (*.json)")
        if not path:
            return
        try:
            self._keymap = KeyMap.from_json(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._show_error("Could not load key map", str(exc))
            return
        self._persist_keymap()
        self._refresh_keymap_views()
        self._set_status(f"Loaded key map from {path}")

    def _on_reset_keymap(self) -> None:
        self._keymap = default_keymap()
        self._persist_keymap()
        self._refresh_keymap_views()
        self._set_status("Key map reset to WASD default")

    def _persist_keymap(self) -> None:
        try:
            save_keymap(self._keymap, self._keymap_path)
        except OSError:
            pass

    def _refresh_keymap_views(self) -> None:
        self._mapper = None
        if self.keymap_chk.isChecked():
            self.screen.set_keymapping(True, self._keymap)
        if self.edit_keys_btn.isChecked():
            self.screen.set_edit_mode(True, self._keymap)

    def _ensure_mapper(self) -> KeyMapper | None:
        if self._adb is None:
            return None
        if self._mapper is None or self._mapper_size != self._device_size:
            self._mapper = KeyMapper(self._adb, self._keymap, self._device_size)
            self._mapper_size = self._device_size
        return self._mapper

    def _on_key_pressed(self, key: str) -> None:
        mapper = self._ensure_mapper()
        if mapper is None:
            return
        try:
            mapper.press(key)
        except Exception as exc:  # noqa: BLE001 - surface, never crash the UI
            self._set_status(str(exc))

    def _on_key_released(self, key: str) -> None:
        mapper = self._ensure_mapper()
        if mapper is None:
            return
        try:
            mapper.release(key)
        except Exception as exc:  # noqa: BLE001 - surface, never crash the UI
            self._set_status(str(exc))

    # -- Helpers -------------------------------------------------------------
    def _with_adb(self, fn) -> None:
        if self._adb is None:
            self._set_status("Start a device first")
            return
        try:
            fn(self._adb)
        except Exception as exc:  # noqa: BLE001 - surface, never crash the UI
            self._set_status(str(exc))

    def _set_status(self, message: str) -> None:
        self.status.setText(message)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
        self._set_status(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._stop_polling()
        if self._session is not None:
            self._session.stop()
        super().closeEvent(event)
