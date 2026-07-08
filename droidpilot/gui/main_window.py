"""The DroidPilot main window."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
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
from ..core.emulator import EmulatorController, EmulatorSession
from ..core.errors import DroidPilotError
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

        self.setWindowTitle("DroidPilot")
        self.resize(1000, 720)
        self._build_ui()
        self._init_sdk()

    # -- UI construction -----------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        self.screen = ScreenView()
        self.screen.tapped.connect(self._on_screen_tap)
        root.addWidget(self.screen, stretch=3)

        side = QVBoxLayout()
        root.addLayout(side, stretch=2)

        side.addWidget(self._build_device_group())
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
        try:
            self._session = self._controller.start(avd)
        except DroidPilotError as exc:
            self._show_error("Failed to start emulator", str(exc))
            return
        self._adb = Adb(self._sdk.adb)  # type: ignore[union-attr]
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_status(f"Starting {avd}… waiting for boot")
        self._start_polling()

    def _on_stop(self) -> None:
        self._stop_polling()
        if self._session is not None:
            self._session.stop()
            self._session = None
        self._adb = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_status("Stopped")

    def _start_polling(self) -> None:
        if self._adb is None:
            return
        self._poller = ScreenPoller(self._adb, self._config.screen_refresh_ms)
        self._poller.frame.connect(self._on_frame)
        self._poller.error.connect(self._set_status)
        self._poller.start()

    def _stop_polling(self) -> None:
        if self._poller is not None:
            self._poller.stop()
            self._poller.wait(2000)
            self._poller = None

    def _on_frame(self, png: bytes) -> None:
        if self._adb is not None:
            try:
                self.screen.set_device_size(*self._adb.screen_size())
            except DroidPilotError:
                pass
        self.screen.update_frame(png)

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
        from pathlib import Path

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

    # -- Helpers -------------------------------------------------------------
    def _with_adb(self, fn) -> None:
        if self._adb is None:
            self._set_status("Start a device first")
            return
        try:
            fn(self._adb)
        except DroidPilotError as exc:
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
