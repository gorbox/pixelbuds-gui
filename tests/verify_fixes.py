"""Focused verification of the settings/EQ/balance/adaptive fixes."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pixelbuds_gui import pbctrl

# --- 1. ANC capability detection against the installed pbpctrl ------------ #
modes = pbctrl.detect_anc_modes()
print("detected anc modes:", modes)
# The three universal modes must always be present; adaptive only if the
# binary advertises it.  Derive the expectation from the binary itself so this
# test stays correct on both 0.1.8 and git-HEAD builds.  (Note: the word
# "adaptive" appears in the help *description* regardless, so we must inspect
# the [possible values: ...] list specifically.)
import re
m = re.search(r"\[possible values:\s*([^\]]*)\]", pbctrl._run("set", "anc", "--help"))
advertised = {v.strip() for v in m.group(1).split(",")} if m else set()
assert {"off", "active", "aware"} <= set(modes) <= set(pbctrl.ANC_STATES)
assert ("adaptive" in modes) == ("adaptive" in advertised), (modes, advertised)

# --- 2. set_anc_loop sends only the modes present in the dict ------------- #
captured = []
orig = pbctrl._run
pbctrl._run = lambda *a, **k: captured.append(a) or ""

# 3-mode dict (0.1.8): must send 3 bools, no adaptive.
pbctrl.set_anc_loop({"off": True, "active": True, "aware": False})
assert captured[0] == ("set", "anc-gesture-loop", "true", "true", "false"), captured[0]
print("3-mode set_anc_loop:", captured[0])

# 4-mode dict (git HEAD): must send 4 bools in off/active/aware/adaptive order.
captured.clear()
pbctrl.set_anc_loop({"off": True, "active": False, "aware": True, "adaptive": True})
assert captured[0] == ("set", "anc-gesture-loop", "true", "false", "true", "true"), captured[0]
print("4-mode set_anc_loop:", captured[0])

pbctrl._run = orig

# --- 3. GUI construction: no adaptive button; slider + checkbox wiring ----- #
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from pixelbuds_gui.main_window import MainWindow

app = QApplication([])
win = MainWindow()

# ANC buttons / loop checkboxes must mirror exactly the detected modes.
btn_labels = list(win._anc_buttons.keys())
print("anc buttons:", btn_labels)
assert btn_labels == modes, btn_labels
assert set(win._loop_checks.keys()) == set(modes)

# Arrow-key path: changing an EQ slider value must schedule the debounced write.
captured.clear()
pbctrl._run = lambda *a, **k: captured.append(a) or ""
win._loading = False
win._eq_sliders[0].setValue(30)  # 3.0 dB -- same signal Qt emits for arrow keys
QTimer.singleShot(600, app.quit)  # let the 250ms debounce fire
app.exec()
eq_calls = [c for c in captured if c and c[0] == "set" and c[1] == "eq"]
print("eq calls after slider change:", eq_calls)
assert eq_calls, "arrow-key EQ change must trigger set eq"
assert eq_calls[0] == ("set", "eq", "--", "3.00", "0.00", "0.00", "0.00", "0.00"), eq_calls[0]

# Balance slider arrow-key path.
captured.clear()
win._balance_slider.setValue(-25)
QTimer.singleShot(600, app.quit)
app.exec()
bal_calls = [c for c in captured if c and c[0] == "set" and c[1] == "balance"]
print("balance calls:", bal_calls)
assert bal_calls and bal_calls[0] == ("set", "balance", "--", "-25"), bal_calls

# Checkbox toggle -> set_bool.
captured.clear()
cb = win._bool_checks["multipoint"]
cb.setChecked(True)  # triggers toggled(True)
# drain queued worker submissions
QTimer.singleShot(400, app.quit)
app.exec()
bool_calls = [c for c in captured if c and c[0] == "set" and c[1] == "multipoint"]
print("multipoint calls:", bool_calls)
assert bool_calls and bool_calls[0] == ("set", "multipoint", "true"), bool_calls

pbctrl._run = orig
print("\nALL FIX VERIFICATIONS PASSED")
