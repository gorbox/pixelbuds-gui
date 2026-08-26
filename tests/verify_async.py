"""Regression coverage for the async worker lifetime + checkbox feedback fixes.

The original bug: `Worker` is a `QRunnable` with default `autoDelete=True`.
After `run()` returned, QThreadPool freed the C++ object while the Python
wrapper (holding `WorkerSignals`) could still be GC'd mid-flight, corrupting
the heap ("free(): invalid pointer") or silently dropping the queued
success/error signal.  The symptom was settings checkboxes that appeared to
"do nothing": the `set` command was sent, but the result/error callback never
landed on the GUI thread.
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from pixelbuds_gui import pbctrl
from pixelbuds_gui.main_window import MainWindow

app = QApplication([])
win = MainWindow()
win._loading = False

# Let the initial refresh_all() settle (it fails on a no-device machine).
QTimer.singleShot(1200, app.quit)
app.exec()

# --- 1. worker lifetime: many rapid workers must all deliver, no crash ----- #
count = {"done": 0, "err": 0}
for i in range(200):
    if i % 2 == 0:
        win._submit(lambda i=i: i, lambda r: count.__setitem__("done", count["done"] + 1), lambda m: count.__setitem__("err", count["err"] + 1))
    else:
        def boom(i=i):
            raise pbctrl.PbctrlError(f"boom {i}")
        win._submit(boom, None, lambda m: count.__setitem__("err", count["err"] + 1))
QTimer.singleShot(3000, app.quit)
app.exec()
assert count == {"done": 100, "err": 100}, count
assert len(win._workers) == 0, "workers must all be released after delivery"
print("1 worker lifetime: 200 workers, no crash, all callbacks delivered")

# Capture originals before any monkeypatching so test 4 can exercise the real
# set_bool_verified even after tests 2/3 clobber the module attributes.
_orig_set = pbctrl.set_bool
_orig_get = pbctrl.get_bool
_orig_verified = pbctrl.set_bool_verified

# --- 2. success path: checkbox stays checked, status confirms -------------- #
pbctrl.set_bool_verified = lambda name, value, device=None: None
cb = win._bool_checks["multipoint"]
cb.setChecked(True)
QTimer.singleShot(1000, app.quit)
app.exec()
assert cb.isChecked() is True
assert "Set Multipoint: on" in win.status_label.text(), win.status_label.text()
print("2 success feedback OK ->", repr(win.status_label.text()))

# --- 3. failure path: checkbox reverts, status names the failed setting ---- #
def fail(name, value, device=None):
    raise pbctrl.PbctrlError("simulated write failure")
pbctrl.set_bool_verified = fail
cb.setChecked(False)  # toggle True -> False; set fails, must revert to True
QTimer.singleShot(1000, app.quit)
app.exec()
assert cb.isChecked() is True, "failed write must revert the checkbox"
assert "Failed to set Multipoint" in win.status_label.text(), win.status_label.text()
print("3 revert-on-failure OK ->", repr(win.status_label.text()))

# --- 4. read-back verification catches firmware that ignores the write ----- #
pbctrl.set_bool_verified = _orig_verified  # undo test 3's clobber
try:
    pbctrl.set_bool = lambda name, value, device=None: None
    pbctrl.get_bool = lambda name, device=None: False  # write "didn't stick"
    try:
        pbctrl.set_bool_verified("multipoint", True)
    except pbctrl.PbctrlError as exc:
        assert "did not apply" in str(exc), str(exc)
    else:
        raise AssertionError("set_bool_verified must raise on read-back mismatch")
finally:
    pbctrl.set_bool_verified, pbctrl.set_bool, pbctrl.get_bool = (
        _orig_verified, _orig_set, _orig_get,
    )
print("4 read-back verification OK")

print("ASYNC FIX VERIFICATIONS PASSED")
