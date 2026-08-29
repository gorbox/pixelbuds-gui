"""Smoke test for the pbpctrl parsers + offscreen GUI construction.

Run: uv run python -m tests.smoke   (or: uv run python tests/smoke.py)
"""
from __future__ import annotations

from pixelbuds_gui import pbctrl

# --- parser tests against pbpctrl's real output formats -------------------- #

battery = pbctrl.parse_battery(
    "case:      85% (not charging)\n"
    "left bud:  90% (not charging)\n"
    "right bud: 88% (charging)\n"
)
assert battery.case.level == 85 and battery.case.state == "not charging"
assert battery.left.level == 90
assert battery.right.level == 88 and battery.right.state == "charging"

battery_unknown = pbctrl.parse_battery(
    "case:      unknown\nleft bud:  unknown\nright bud: unknown\n"
)
assert battery_unknown.case is None and battery_unknown.left is None

assert pbctrl.parse_anc("active\n") == "active"
assert pbctrl.parse_anc("unknown (3)\n") == "unknown"

assert pbctrl.parse_eq("[-6.00, 0.00, 1.50, 2.00, 3.50]\n") == [-6.0, 0.0, 1.5, 2.0, 3.5]

assert pbctrl.parse_balance("left: 70%, right: 100%\n") == 30
assert pbctrl.parse_balance("left: 100%, right: 70%\n") == -30
assert pbctrl.parse_balance("left: 100%, right: 100%\n") == 0

assert pbctrl.parse_gesture_control("left: anc, right: assistant\n") == ("anc", "assistant")

placement = pbctrl.parse_placement(
    "clock: 123 ms\n\n"
    "placement:\n"
    "  left bud:  in case\n"
    "  right bud: out of case\n"
)
assert placement.left_in_case is True and placement.right_in_case is False
assert pbctrl.parse_placement("").left_in_case is None

# `show runtime` emits battery AND placement in one blob. parse_battery must
# ignore the placement lines ("in case" / "out of case") and not overwrite the
# battery fields it already parsed above them.
runtime_battery = pbctrl.parse_battery(
    "clock: 123 ms\n\n"
    "battery:\n"
    "  case:      85% (not charging)\n"
    "  left bud:  90% (not charging)\n"
    "  right bud: 88% (charging)\n\n"
    "placement:\n"
    "  left bud:  in case\n"
    "  right bud: out of case\n"
)
assert runtime_battery.case.level == 85
assert runtime_battery.left.level == 90
assert runtime_battery.right.level == 88

# pbpctrl's `HoldGestureAction` enum only defines `Anc` and `Assistant`; any
# other gesture action makes clap reject the command (and the GUI report a
# disconnect).  Guard against invalid actions being reintroduced.
assert set(pbctrl.GESTURE_ACTIONS) == {"anc", "assistant"}, pbctrl.GESTURE_ACTIONS

loop = pbctrl.parse_anc_loop("[active, off, adaptive]\n")
assert loop == {"off": True, "active": True, "aware": False, "adaptive": True}

assert pbctrl.get_bool.__name__  # just ensure importable

print("parsers: OK")


# --- command-construction regression tests --------------------------------- #
# pbpctrl's clap parser rejects a leading "-" (e.g. `set balance -50` →
# "unexpected argument '-5'").  set_eq / set_balance must always insert "--"
# so negative band / balance values reach pbpctrl as positional args.
_captured = []


def _fake_run(*args, device=None, timeout=20.0):
    _captured.append(args)
    return ""


orig_run = pbctrl._run
pbctrl._run = _fake_run
try:
    pbctrl.set_eq([-3.0, 2.5, 0.0, -1.25, 4.0])
    pbctrl.set_balance(-42)
    pbctrl.set_balance(0)
finally:
    pbctrl._run = orig_run

assert len(_captured) == 3
assert _captured[0] == ("set", "eq", "--", "-3.00", "2.50", "0.00", "-1.25", "4.00")
assert _captured[1] == ("set", "balance", "--", "-42")
assert _captured[2] == ("set", "balance", "--", "0")

print("negative-value command construction: OK")


# get_runtime must issue a single `show runtime` call and return both the
# battery and the placement from that one snapshot.
_runtime_calls = []


def _fake_runtime(*args, device=None, timeout=20.0):
    _runtime_calls.append(args)
    return (
        "clock: 123 ms\n\n"
        "battery:\n"
        "  case:      72% (charging)\n"
        "  left bud:  95% (not charging)\n"
        "  right bud: 40% (not charging)\n\n"
        "placement:\n"
        "  left bud:  in case\n"
        "  right bud: out of case\n"
    )


orig_run = pbctrl._run
pbctrl._run = _fake_runtime
try:
    b, p = pbctrl.get_runtime()
finally:
    pbctrl._run = orig_run

assert _runtime_calls == [("show", "runtime")], _runtime_calls
assert b.case.level == 72 and b.case.state == "charging"
assert b.left.level == 95 and b.right.level == 40
assert p.left_in_case is True and p.right_in_case is False

print("get_runtime single-call consolidation: OK")


# --- `show hardware` serial parsing --------------------------------------- #
serials = pbctrl.parse_keyed(
    "\n".join(
        [
            "serial numbers:",
            "  case:      AB12CD",
            "  left bud:  EF34GH",
            "  right bud: IJ56KL",
        ]
    )
)
assert serials["case"] == "AB12CD"
assert serials["left bud"] == "EF34GH"
assert serials["right bud"] == "IJ56KL"

print("serials parsing: OK")


# --- notifications: detection + delivery ---------------------------------- #
from types import SimpleNamespace  # noqa: E402

from pixelbuds_gui import notifications as notif  # noqa: E402
from pixelbuds_gui.notifications import (  # noqa: E402
    LowBatteryMonitor,
    notify_low_battery,
    send_notification,
)


def _report(left, right, case):
    def comp(level):
        return None if level is None else SimpleNamespace(level=level)

    return SimpleNamespace(left=comp(left), right=comp(right), case=comp(case))


mon = LowBatteryMonitor(threshold=20, hysteresis=5)

crossed = mon.check(_report(15, 60, None))
assert crossed == [("left", 15)], crossed
assert mon.check(_report(15, 60, None)) == []  # no repeat while still below
assert mon.check(_report(15, 18, None)) == [("right", 18)]
assert mon.check(_report(30, 18, None)) == []  # left re-arms above 25
assert mon.check(_report(14, 18, None)) == [("left", 14)]  # and re-notifies
assert mon.check(_report(14, 18, 5)) == [("case", 5)]

# Unknown components are skipped and leave state untouched.
mon2 = LowBatteryMonitor()
assert mon2.check(_report(None, None, None)) == []

print("low-battery monitor: OK")


_sent = []
_orig_send = notif.send_notification


def _fake_send(title, body, urgency="normal"):
    _sent.append((title, body, urgency))
    return True


notif.send_notification = _fake_send
try:
    notify_low_battery([("left", 12), ("case", 8)])
finally:
    notif.send_notification = _orig_send

assert len(_sent) == 1
assert _sent[0][0] == "Pixel Buds low battery"
assert "Left bud at 12%" in _sent[0][1]
assert "Case at 8%" in _sent[0][1]
assert _sent[0][2] == "critical"

# No crossings -> no notification.
notif.send_notification = _fake_send
_sent.clear()
try:
    notify_low_battery([])
finally:
    notif.send_notification = _orig_send
assert _sent == []

# Missing notify-send binary -> send_notification no-ops to False (never raises).
_orig_which = notif.shutil.which
notif.shutil.which = lambda _p: None
try:
    assert send_notification("t", "b") is False
finally:
    notif.shutil.which = _orig_which

print("notifications: OK")



# --- offscreen GUI construction ------------------------------------------- #
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pixelbuds_gui.main_window import MainWindow  # noqa: E402

app = QApplication([])
win = MainWindow()
win.show()

# Drive the event loop briefly so the async refresh (which will fail with
# "no device" on this Bluetooth-less host) resolves and updates the status.
from PySide6.QtCore import QTimer  # noqa: E402

QTimer.singleShot(1500, app.quit)
app.exec()

# Status should have been set to disconnected by the error path.
txt = win.status_label.text()
assert txt == "Not connected", f"unexpected status: {txt!r}"
assert win.refresh_btn.isEnabled()

print("GUI construction + async error path: OK  (status =", txt + ")")
