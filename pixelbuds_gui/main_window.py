"""Qt main window for pixelbuds-gui.

All blocking `pbpctrl` calls run on a background thread pool; results are
applied to the widgets on the GUI thread via Qt signals.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThreadPool, QRunnable, QObject, Signal, Slot, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import pbctrl
from .pbctrl import (
    BOOL_SETTINGS,
    GESTURE_ACTIONS,
    NoDeviceError,
    PbctrlError,
)

# Human-friendly labels.
ANC_LABELS = {
    "off": "Off",
    "active": "ANC",
    "aware": "Transparency",
    "adaptive": "Adaptive",
}
GESTURE_LABELS = {
    "anc": "Toggle ANC",
    "assistant": "Assistant",
}
BOOL_LABELS = {
    "multipoint": "Multipoint",
    "ohd": "On-head detection",
    "speech-detection": "Speech detection",
    "gestures": "Gestures",
    "volume-eq": "Volume-dependent EQ",
    "volume-exposure-notifications": "Volume exposure notifications",
    "auto-ota": "Automatic updates",
    "diagnostics": "Diagnostics",
    "mono": "Mono audio",
}
EQ_BAND_LABELS = ("Low Bass", "Bass", "Mid", "Treble", "Upper Treble")

EQ_PRESETS = {
    "Flat": [0.0, 0.0, 0.0, 0.0, 0.0],
    "Bass Boost": [3.0, 2.0, 0.0, 0.0, 0.0],
    "Treble Boost": [0.0, 0.0, 0.0, 2.0, 3.0],
    "Vocal": [0.0, 1.0, 2.0, 1.0, 0.0],
}

DARK_QSS = """
QWidget { background-color: #1b1e24; color: #e8eaf0; font-size: 13px; }
QMainWindow { background-color: #14161b; }
QFrame#card {
    background-color: #1b1e24; border: 1px solid #2a2e38; border-radius: 10px;
}
QLabel#sectionTitle { font-size: 12px; font-weight: 600; color: #9aa3b2; }
QLabel#bigValue { font-size: 26px; font-weight: 700; }
QLabel#muted { color: #9aa3b2; }
QLabel#statusConnected { color: #4ade80; font-weight: 600; }
QLabel#statusDisconnected { color: #f87171; font-weight: 600; }
QLabel#statusBusy { color: #fbbf24; font-weight: 600; }
QPushButton {
    background-color: #262b34; border: 1px solid #343a46; border-radius: 8px;
    padding: 8px 12px; color: #e8eaf0;
}
QPushButton:hover { background-color: #2f3540; }
QPushButton:checked, QPushButton:active {
    background-color: #3b82f6; border-color: #3b82f6; color: white;
}
QPushButton:pressed { background-color: #2563eb; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; }
QComboBox, QSlider::groove:horizontal {
    background-color: #262b34; border: 1px solid #343a46; border-radius: 6px;
}
QComboBox { padding: 6px 8px; }
QComboBox QAbstractItemView { background-color: #262b34; color: #e8eaf0; selection-background-color: #3b82f6; }
QSlider::groove:horizontal { height: 6px; }
QSlider::handle:horizontal { width: 18px; margin: -6px 0; background: #3b82f6; border-radius: 9px; }
QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 6px; }
QSlider::groove:vertical { width: 6px; }
QSlider::handle:vertical { height: 18px; margin: 0 -6px; background: #3b82f6; border-radius: 9px; }
QScrollArea { border: none; }
"""


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    """Run a callable on the thread pool and emit its result / exception."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(result)


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pixel Buds Pro")
        self.setMinimumSize(480, 640)
        self.resize(540, 820)

        self._pool = QThreadPool.globalInstance()
        self._loading = False  # suppress UI->set loops during refresh

        # Only expose the ANC modes the installed pbpctrl can actually set
        # (0.1.8 lacks "adaptive").  Detected once, synchronously -- this is a
        # fast `--help` subprocess, not a Bluetooth round-trip.
        self._anc_modes = pbctrl.detect_anc_modes()

        # Debounce timers: slider drags and arrow-key presses fire `valueChanged`
        # continuously, so coalesce the bursts into a single pbpctrl write
        # instead of one slow RFCOMM handshake per tick.
        self._eq_debounce = QTimer(self)
        self._eq_debounce.setSingleShot(True)
        self._eq_debounce.setInterval(250)
        self._eq_debounce.timeout.connect(self._set_eq)

        self._balance_debounce = QTimer(self)
        self._balance_debounce.setSingleShot(True)
        self._balance_debounce.setInterval(250)
        self._balance_debounce.timeout.connect(self._set_balance)

        self._build_ui()

        self._battery_timer = QTimer(self)
        self._battery_timer.setInterval(30_000)
        self._battery_timer.timeout.connect(self._refresh_battery)
        self._battery_timer.start()

        self.refresh_all()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("Pixel Buds Pro")
        title.setFont(QFont(title.font().family(), 18, QFont.Weight.Bold))
        self.status_label = QLabel("Checking…")
        self.status_label.setObjectName("statusBusy")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.status_label)
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setToolTip("Refresh all settings")
        self.refresh_btn.clicked.connect(self.refresh_all)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(10)

        self._build_battery_section(self._body_layout)
        self._build_anc_section(self._body_layout)
        self._build_eq_section(self._body_layout)
        self._build_audio_section(self._body_layout)
        self._build_gesture_section(self._body_layout)
        self._build_settings_section(self._body_layout)
        self._build_info_section(self._body_layout)
        self._body_layout.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll)

        footer = QLabel(f"pixelbuds-gui v{__version__}  ·  driven by pbpctrl")
        footer.setObjectName("muted")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    def _add_card(self, layout: QVBoxLayout) -> QVBoxLayout:
        card = _card()
        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(10)
        layout.addWidget(card)
        return inner

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    # ----------------------------------------------------------- sections --

    def _build_battery_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        inner.addWidget(self._section_title("BATTERY"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self._batt_widgets = {}
        for key, label in (("left", "Left"), ("right", "Right"), ("case", "Case")):
            box = QVBoxLayout()
            title = QLabel(label)
            title.setObjectName("muted")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value = QLabel("—")
            value.setObjectName("bigValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            state = QLabel("")
            state.setObjectName("muted")
            state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(title)
            box.addWidget(value)
            box.addWidget(state)
            row.addLayout(box)
            self._batt_widgets[key] = (value, state)
            if key == "case":
                # The Pixel Buds Pro case has no Bluetooth radio of its own;
                # its charge is only relayed through a bud seated in the case,
                # and only while that bud is awake enough to report it (case
                # lid open). It reads "—" otherwise.
                title.setToolTip(
                    "The case has no Bluetooth radio of its own; its charge is "
                    "relayed through a bud seated in it. It reads \"—\" when no "
                    "seated bud is awake to relay it (case empty, or lid closed)."
                )
                value.setToolTip(title.toolTip())
        inner.addLayout(row)
        # Per-bud placement (in case / out of case). Reported by the buds
        # themselves and may lag or read "out of case" while the case lid is
        # closed (a seated bud sleeps and stops relaying its state).
        self._place_label = QLabel("")
        self._place_label.setObjectName("muted")
        self._place_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._place_label.setToolTip(
            "Placement is reported by the buds and can lag while the case lid "
            "is closed, when a seated bud sleeps and stops relaying its state."
        )
        inner.addWidget(self._place_label)

    def _build_anc_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        inner.addWidget(self._section_title("ACTIVE NOISE CANCELLING"))
        anc_row = QHBoxLayout()
        self._anc_group = QButtonGroup(self)
        self._anc_group.setExclusive(True)
        self._anc_buttons = {}
        for state in self._anc_modes:
            btn = QPushButton(ANC_LABELS[state])
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, s=state: self._set_anc(s))
            self._anc_group.addButton(btn)
            self._anc_buttons[state] = btn
            anc_row.addWidget(btn)
        inner.addLayout(anc_row)

        inner.addWidget(self._section_title("ANC GESTURE LOOP (cycle modes)"))
        loop_row = QHBoxLayout()
        self._loop_checks = {}
        for mode in self._anc_modes:
            cb = QCheckBox(ANC_LABELS[mode])
            cb.toggled.connect(lambda *_a, m=mode: self._set_anc_loop())
            self._loop_checks[mode] = cb
            loop_row.addWidget(cb)
        inner.addLayout(loop_row)

    def _build_eq_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        header = QHBoxLayout()
        header.addWidget(self._section_title("EQUALIZER"))
        header.addStretch(1)
        for name in EQ_PRESETS:
            b = QPushButton(name)
            b.setProperty("class", "small")
            b.clicked.connect(lambda _=False, n=name: self._apply_eq_preset(n))
            header.addWidget(b)
        inner.addLayout(header)

        eq_row = QHBoxLayout()
        self._eq_sliders = {}
        self._eq_value_labels = {}
        for i, label in enumerate(EQ_BAND_LABELS):
            col = QVBoxLayout()
            col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sl = QSlider(Qt.Orientation.Vertical)
            sl.setRange(-60, 60)  # -6.0 .. 6.0 in 0.1 steps
            sl.setFixedHeight(140)
            # valueChanged (not sliderReleased) so arrow-key edits apply too;
            # the handler debounces and guards against refresh-driven changes.
            sl.valueChanged.connect(self._eq_value_changed)
            val = QLabel("0.0")
            val.setObjectName("muted")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name = QLabel(label)
            name.setObjectName("muted")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(sl)
            col.addWidget(val)
            col.addWidget(name)
            eq_row.addLayout(col)
            self._eq_sliders[i] = sl
            self._eq_value_labels[i] = val
        inner.addLayout(eq_row)

    def _build_audio_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        inner.addWidget(self._section_title("AUDIO"))

        bal_row = QHBoxLayout()
        bal_row.addWidget(QLabel("L"))
        self._balance_slider = QSlider(Qt.Orientation.Horizontal)
        self._balance_slider.setRange(-100, 100)
        self._balance_slider.valueChanged.connect(self._balance_value_changed)
        self._balance_label = QLabel("0")
        self._balance_label.setObjectName("muted")
        self._balance_label.setMinimumWidth(30)
        self._balance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bal_row.addWidget(self._balance_slider, 1)
        bal_row.addWidget(self._balance_label)
        bal_row.addWidget(QLabel("R"))
        inner.addLayout(bal_row)

        self._mono_check = QCheckBox("Mono audio")
        self._mono_check.toggled.connect(lambda v: self._set_bool("mono", v))
        inner.addWidget(self._mono_check)

    def _build_gesture_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        inner.addWidget(self._section_title("GESTURES"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("Hold left:"), 0, 0)
        grid.addWidget(QLabel("Hold right:"), 1, 0)
        self._gesture_combos = {}
        for row, side in ((0, "left"), (1, "right")):
            combo = QComboBox()
            for action in GESTURE_ACTIONS:
                combo.addItem(GESTURE_LABELS[action], action)
            combo.currentIndexChanged.connect(lambda *_a, s=side: self._set_gestures())
            grid.addWidget(combo, row, 1)
            self._gesture_combos[side] = combo
        inner.addLayout(grid)

    def _build_settings_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        inner.addWidget(self._section_title("SETTINGS"))
        self._bool_checks = {}
        for name in BOOL_SETTINGS:
            if name == "mono":
                continue  # handled in the audio section
            cb = QCheckBox(BOOL_LABELS[name])
            cb.toggled.connect(lambda v, n=name: self._set_bool(n, v))
            inner.addWidget(cb)
            self._bool_checks[name] = cb

    def _build_info_section(self, root: QVBoxLayout) -> None:
        inner = self._add_card(root)
        inner.addWidget(self._section_title("ABOUT"))
        self._firmware_label = QLabel("Firmware: —")
        self._firmware_label.setObjectName("muted")
        inner.addWidget(self._firmware_label)

    # ------------------------------------------------------------ refresh --

    def refresh_all(self) -> None:
        self._set_status("busy", "Refreshing…")
        self.refresh_btn.setEnabled(False)
        self._submit(self._load_all, self._apply_all, self._on_error)

    def _refresh_battery(self) -> None:
        if self._loading:
            return
        self._submit(self._load_battery, self._apply_battery_state, self._on_battery_error)

    @staticmethod
    def _load_battery():
        # One `show runtime` call returns both battery and placement from the
        # same runtime-info snapshot (see pbctrl.get_runtime).
        return pbctrl.get_runtime()

    def _apply_battery_state(self, result) -> None:
        report, placement = result
        self._apply_battery(report)
        self._apply_placement(placement)

    @staticmethod
    def _load_all():
        data = {}
        data["battery"], data["placement"] = pbctrl.get_runtime()
        data["anc"] = pbctrl.get_anc()
        data["eq"] = pbctrl.get_eq()
        data["balance"] = pbctrl.get_balance()
        data["gesture"] = pbctrl.get_gesture_control()
        data["loop"] = pbctrl.get_anc_loop()
        data["bools"] = {n: pbctrl.get_bool(n) for n in BOOL_SETTINGS}
        data["firmware"] = pbctrl.get_firmware()
        return data

    def _apply_all(self, data: dict) -> None:
        self._loading = True
        try:
            self._apply_battery(data["battery"])
            self._apply_placement(data.get("placement"))
            self._apply_anc(data["anc"])
            self._apply_eq(data["eq"])
            self._apply_balance(data["balance"])
            self._apply_gesture(data["gesture"])
            self._apply_loop(data["loop"])
            self._apply_bools(data["bools"])
            self._apply_firmware(data["firmware"])
            self._set_status("connected", "Connected")
        finally:
            self._loading = False
            self.refresh_btn.setEnabled(True)

    def _apply_battery(self, report) -> None:
        for key in ("left", "right", "case"):
            value_lbl, state_lbl = self._batt_widgets[key]
            info = getattr(report, key)
            if info and info.level is not None:
                value_lbl.setText(f"{info.level}%")
                state_lbl.setText(info.state or "")
            else:
                value_lbl.setText("—")
                state_lbl.setText("")

    def _apply_placement(self, placement) -> None:
        if placement is None:
            self._place_label.setText("")
            return
        parts = []
        for side, label in (("left", "Left"), ("right", "Right")):
            in_case = getattr(placement, f"{side}_in_case", None)
            if in_case is None:
                parts.append(f"{label}: unknown")
            else:
                parts.append(f"{label}: {'in case' if in_case else 'out of case'}")
        self._place_label.setText("   ·   ".join(parts))

    def _apply_anc(self, state: str) -> None:
        btn = self._anc_buttons.get(state)
        if btn:
            btn.setChecked(True)

    def _apply_eq(self, bands: list[float]) -> None:
        for i, val in enumerate(bands):
            if i >= len(self._eq_sliders):
                break
            self._eq_sliders[i].setValue(round(val * 10))
            self._eq_value_labels[i].setText(f"{val:.1f}")

    def _apply_balance(self, value: int) -> None:
        self._balance_slider.setValue(value)
        self._balance_label.setText(str(value))

    def _apply_gesture(self, gesture: tuple[str, str]) -> None:
        for side, combo in self._gesture_combos.items():
            action = gesture[0] if side == "left" else gesture[1]
            idx = combo.findData(action)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _apply_loop(self, modes: dict[str, bool]) -> None:
        for mode, cb in self._loop_checks.items():
            cb.setChecked(modes.get(mode, False))

    def _apply_bools(self, bools: dict[str, bool]) -> None:
        for name, value in bools.items():
            if name == "mono":
                self._mono_check.setChecked(value)
            elif name in self._bool_checks:
                self._bool_checks[name].setChecked(value)

    def _apply_firmware(self, firmware: dict[str, str]) -> None:
        parts = []
        for key in ("case", "left bud", "right bud"):
            if key in firmware and firmware[key]:
                parts.append(f"{key}: {firmware[key]}")
        self._firmware_label.setText("Firmware — " + "   ".join(parts) if parts else "Firmware: —")

    # ------------------------------------------------------------ actions --

    def _set_anc(self, state: str) -> None:
        self._submit(pbctrl.set_anc, None, self._on_error, state)

    def _eq_value_changed(self) -> None:
        # Fires on every slider change (drag, arrow-key, or programmatic).
        # Update the readout live, but only schedule a write when the change
        # came from the user -- refresh-driven `setValue` calls happen under
        # `_loading` and must not echo back to the buds.
        if self._loading:
            return
        for i in range(5):
            self._eq_value_labels[i].setText(f"{self._eq_sliders[i].value() / 10.0:.1f}")
        self._eq_debounce.start()

    def _set_eq(self) -> None:
        bands = [self._eq_sliders[i].value() / 10.0 for i in range(5)]
        for i, val in enumerate(bands):
            self._eq_value_labels[i].setText(f"{val:.1f}")
        self._submit(pbctrl.set_eq, None, self._on_error, bands)

    def _apply_eq_preset(self, name: str) -> None:
        bands = EQ_PRESETS[name]
        self._loading = True
        try:
            self._apply_eq(bands)
        finally:
            self._loading = False
        self._submit(pbctrl.set_eq, None, self._on_error, bands)

    def _set_balance(self) -> None:
        value = self._balance_slider.value()
        self._balance_label.setText(str(value))
        self._submit(pbctrl.set_balance, None, self._on_error, value)

    def _balance_value_changed(self) -> None:
        # Same as _eq_value_changed: apply arrow-key edits, ignore refresh echo.
        if self._loading:
            return
        self._balance_label.setText(str(self._balance_slider.value()))
        self._balance_debounce.start()

    def _set_gestures(self) -> None:
        if self._loading:
            return
        left = self._gesture_combos["left"].currentData()
        right = self._gesture_combos["right"].currentData()
        self._submit(pbctrl.set_gesture_control, None, self._on_error, left, right)

    def _set_anc_loop(self) -> None:
        if self._loading:
            return
        modes = {m: cb.isChecked() for m, cb in self._loop_checks.items()}
        if sum(modes.values()) < 2:
            return  # pbpctrl requires at least 2 modes
        self._submit(pbctrl.set_anc_loop, None, self._on_error, modes)

    def _set_bool(self, name: str, value: bool) -> None:
        if self._loading:
            return
        self._submit(pbctrl.set_bool, None, self._on_error, name, value)

    # ------------------------------------------------------------- status --

    def _set_status(self, kind: str, text: str) -> None:
        obj = {"connected": "statusConnected",
               "disconnected": "statusDisconnected",
               "busy": "statusBusy"}.get(kind, "statusBusy")
        self.status_label.setObjectName(obj)
        # force re-polish so the dynamic objectName restyle applies
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(text)

    def _on_error(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self._set_status("disconnected", "Not connected")
        self.status_label.setToolTip(message)

    def _on_battery_error(self, message: str) -> None:
        # Battery polling failure should not nuke the whole UI state.
        self.status_label.setToolTip(message)

    # ----------------------------------------------------------- plumbing --

    def _submit(self, fn, on_done, on_error, *args) -> None:
        worker = Worker(fn, *args)
        if on_done is not None:
            worker.signals.finished.connect(on_done)
        if on_error is not None:
            worker.signals.error.connect(on_error)
        self._pool.start(worker)


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    win = MainWindow()
    win.show()
    return app.exec()
