"""Read pbwatch daemon state files as a contention-free data source.

``pbutils/bin/pbwatch`` holds a *persistent* RFCOMM connection (channel 2) and
writes its latest battery + ANC snapshot to ``$XDG_RUNTIME_DIR/pbwatch/``.
When that daemon is running, the GUI can read those files directly instead of
opening a second RFCOMM connection through ``pbpctrl`` — avoiding the maestro
handoff contention the two connections otherwise fight over.

File format (written by pbwatch, see pbutils/bin/pbwatch)::

    battery:
        left=<int>              # -1 = bud seated in case (individual level unknown)
        left_charging=<bool>
        right=<int>
        right_charging=<bool>
        case=<int>              # -1 = case charge not relayed (lid shut / none seated)
        case_charging=<bool>
    anc:
        <state>                 # noise_cancellation | transparency | adaptive | off
        <mode>,<mode>,...       # supported modes (optional second line)

pbwatch's ANC names map onto the GUI/pbpctrl names as::

    noise_cancellation -> active
    transparency       -> aware
    adaptive           -> adaptive
    off                -> off

Every function here is a pure filesystem read — no RFCOMM, no subprocess, no
dbus — so it is safe to call on the GUI's 30 s timer. Each returns ``None``
when the daemon isn't running or its files are stale; callers MUST fall back to
``pbctrl``. The freshness window is overridable via ``PBWATCH_FRESH_SECONDS``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from .pbctrl import BatteryInfo, BatteryReport, PlacementReport

_FRESH_SECONDS_DEFAULT = 90

_PBWATCH_ANC_TO_GUI = {
    "noise_cancellation": "active",
    "transparency": "aware",
    "adaptive": "adaptive",
    "off": "off",
}


def _state_dir() -> str:
    return os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
        "pbwatch",
    )


def _fresh_seconds() -> float:
    raw = os.environ.get("PBWATCH_FRESH_SECONDS")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(_FRESH_SECONDS_DEFAULT)


def _file_fresh(path: str) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) <= _fresh_seconds()
    except OSError:
        return False


def _int_or_none(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _in_case(raw: Optional[str]) -> Optional[bool]:
    """Map a battery byte to placement. ``-1`` is pbwatch's 'seated in case'
    sentinel; anything else means the bud is reporting from outside the case.
    A missing/unparseable value is an unknown placement."""
    if raw is None:
        return None
    level = _int_or_none(raw)
    if level is None:
        return None
    return level == -1


def read_battery() -> Optional[tuple[BatteryReport, PlacementReport]]:
    """Return ``(battery, placement)`` from pbwatch's state file, or ``None``.

    ``None`` means the daemon isn't producing fresh data — the caller must fall
    back to ``pbctrl.get_runtime()``.
    """
    path = os.path.join(_state_dir(), "battery")
    if not _file_fresh(path):
        return None

    kv: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, _, value = line.partition("=")
                    kv[key.strip()] = value.strip()
    except OSError:
        return None

    def _info(key: str) -> Optional[BatteryInfo]:
        level = _int_or_none(kv.get(key))
        if level is None or level < 0:
            # < 0 is pbwatch's 'in case / unknown' sentinel — match pbpctrl's
            # "unknown" so the GUI renders it as "—" (placement carries the
            # in-case detail instead).
            return None
        charging = kv.get(f"{key}_charging", "") == "true"
        return BatteryInfo(
            level=level,
            state="charging" if charging else "not charging",
        )

    report = BatteryReport(
        case=_info("case"),
        left=_info("left"),
        right=_info("right"),
    )
    placement = PlacementReport(
        left_in_case=_in_case(kv.get("left")),
        right_in_case=_in_case(kv.get("right")),
    )
    return report, placement


def read_anc() -> Optional[str]:
    """Return the active ANC mode in GUI/pbpctrl naming, or ``None``.

    ``None`` covers both a stale/missing file and an unrecognized mode — the
    caller must fall back to ``pbctrl.get_anc()``.
    """
    path = os.path.join(_state_dir(), "anc")
    if not _file_fresh(path):
        return None
    try:
        with open(path) as f:
            lines = f.read().strip().splitlines()
    except OSError:
        return None
    if not lines:
        return None
    return _PBWATCH_ANC_TO_GUI.get(lines[0].strip())


@dataclass
class PbwatchState:
    battery: BatteryReport
    placement: PlacementReport
    anc: Optional[str] = None  # None -> caller falls back to pbctrl for ANC


def read_state() -> Optional[PbwatchState]:
    """Combined snapshot, or ``None`` if pbwatch isn't producing fresh data.

    Battery is the gate: if it's stale/absent the daemon isn't active, so the
    whole snapshot is considered unavailable. ANC may independently be ``None``
    (e.g. the device hasn't reported a mode yet).
    """
    battery = read_battery()
    if battery is None:
        return None
    return PbwatchState(battery=battery[0], placement=battery[1], anc=read_anc())
