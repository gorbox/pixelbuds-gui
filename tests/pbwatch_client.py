"""Tests for pbwatch_client — pbwatch state-file parsing + ANC name mapping.

Run: uv run python -m tests.pbwatch_client   (or: uv run python tests/pbwatch_client.py)

These exercise the pure filesystem reader without any Bluetooth or pbpctrl, by
pointing XDG_RUNTIME_DIR at a temp directory holding fake pbwatch state files.
"""
from __future__ import annotations

import os
import tempfile
import time

from pixelbuds_gui import pbwatch_client


def _write(tmp: str, name: str, content: str) -> str:
    d = os.path.join(tmp, "pbwatch")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(content)
    return path


def test_battery_full() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        _write(
            tmp,
            "battery",
            "left=90\nleft_charging=false\n"
            "right=88\nright_charging=true\n"
            "case=85\ncase_charging=false\n",
        )
        report, placement = pbwatch_client.read_battery()
        assert report.left.level == 90 and report.left.state == "not charging"
        assert report.right.level == 88 and report.right.state == "charging"
        assert report.case.level == 85 and report.case.state == "not charging"
        assert placement.left_in_case is False
        assert placement.right_in_case is False


def test_battery_in_case_sentinel() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        # -1 = bud seated in case: individual level unknown, placement in-case.
        _write(
            tmp,
            "battery",
            "left=-1\nleft_charging=false\n"
            "right=72\nright_charging=true\n"
            "case=90\ncase_charging=true\n",
        )
        report, placement = pbwatch_client.read_battery()
        assert report.left is None  # renders "—", like pbpctrl "unknown"
        assert report.right.level == 72
        assert report.case.level == 90 and report.case.state == "charging"
        assert placement.left_in_case is True
        assert placement.right_in_case is False


def test_battery_case_unknown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        _write(tmp, "battery", "left=70\nleft_charging=false\n"
                 "right=70\nright_charging=false\ncase=-1\ncase_charging=false\n")
        report, _ = pbwatch_client.read_battery()
        assert report.case is None  # case charge not relayed


def test_anc_mapping() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        for raw, expected in (
            ("noise_cancellation", "active"),
            ("transparency", "aware"),
            ("adaptive", "adaptive"),
            ("off", "off"),
        ):
            _write(tmp, "anc", raw + "\nnoise_cancellation,transparency,off\n")
            assert pbwatch_client.read_anc() == expected, (raw, expected)


def test_anc_unknown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        _write(tmp, "anc", "not_a_mode\n")
        assert pbwatch_client.read_anc() is None


def test_stale_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        os.environ["PBWATCH_FRESH_SECONDS"] = "1"
        path = _write(tmp, "battery", "left=50\nleft_charging=false\n"
                      "right=50\nright_charging=false\ncase=50\ncase_charging=false\n")
        # Force the mtime well into the past.
        old = time.time() - 60
        os.utime(path, (old, old))
        assert pbwatch_client.read_battery() is None
        assert pbwatch_client.read_state() is None


def test_missing_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        assert pbwatch_client.read_battery() is None
        assert pbwatch_client.read_anc() is None
        assert pbwatch_client.read_state() is None


def test_read_state_combined() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_RUNTIME_DIR"] = tmp
        _write(tmp, "battery", "left=80\nleft_charging=true\n"
               "right=80\nright_charging=true\ncase=60\ncase_charging=false\n")
        _write(tmp, "anc", "noise_cancellation\ntransparency,off,noise_cancellation\n")
        state = pbwatch_client.read_state()
        assert state is not None
        assert state.battery.left.level == 80
        assert state.anc == "active"  # noise_cancellation -> active


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("all pbwatch_client tests passed")
