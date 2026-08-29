"""Backend wrapper around the `pbpctrl` CLI (qzed/pbpctrl).

All communication with the buds goes through the `pbpctrl` binary. This module
invokes it via subprocess and parses its human-readable output into typed
Python values. It is deliberately free of any Qt imports so it can be unit
tested and reused independently of the GUI.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

PBPCTRL = shutil.which("pbpctrl") or "pbpctrl"

# If set, always pass this address to pbpctrl (e.g. "AA:BB:CC:DD:EE:FF").
# If None, pbpctrl auto-detects the paired buds.
DEFAULT_DEVICE: Optional[str] = None

# Substrings in pbpctrl/BlueZ error output that mean "no buds reachable" rather
# than "the firmware refused a write".  Distinguishing these lets the GUI show
# an honest "Not connected" for a missing device instead of implying a write
# failed.  "not present" covers BlueZ's "the target object was either not
# present or removed" — the error you get when the host has no Bluetooth
# adapter at all (or the buds have gone out of range).
_NO_DEVICE_HINTS = (
    "no compatible device",
    "no default adapter",
    "not available",
    "not present",
)


def _is_no_device_message(msg: str) -> bool:
    low = msg.lower()
    return any(hint in low for hint in _NO_DEVICE_HINTS)

# ANC states understood by `pbpctrl set anc <state>`.
ANC_STATES = ("off", "active", "aware", "adaptive")

# Actions understood by `pbpctrl set gesture-control <left> <right>`.
# pbpctrl's `HoldGestureAction` enum only defines `Anc` and `Assistant`, so any
# other value (e.g. "next", "play-pause") makes clap reject the command and
# pbpctrl exits non-zero -- which the GUI surfaces as a disconnect.
GESTURE_ACTIONS = (
    "anc",
    "assistant",
)

# The four ANC modes that participate in the ANC gesture loop.
# NOTE: order matters for `set anc-gesture-loop <off> <active> <aware> <adaptive>`.
ANC_LOOP_MODES = ("off", "active", "aware", "adaptive")

# Boolean settings exposed by `pbpctrl get/set <name> <true|false>`.
BOOL_SETTINGS = (
    "auto-ota",
    "ohd",
    "gestures",
    "diagnostics",
    "multipoint",
    "volume-eq",
    "mono",
    "volume-exposure-notifications",
    "speech-detection",
)


class PbctrlError(Exception):
    """Raised when pbpctrl fails for any reason."""


class NoDeviceError(PbctrlError):
    """Raised when no compatible Pixel Buds are paired / reachable."""


def _run(*args: str, device: Optional[str] = None, timeout: float = 20.0) -> str:
    cmd = [PBPCTRL]
    dev = device if device is not None else DEFAULT_DEVICE
    if dev:
        cmd += ["--device", dev]
    cmd += [str(a) for a in args]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:  # pragma: no cover - depends on env
        raise PbctrlError(
            "pbpctrl not found on PATH. Install it with: paru -S pbpctrl"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PbctrlError(f"pbpctrl timed out after {timeout:.0f}s") from exc

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        if _is_no_device_message(msg):
            raise NoDeviceError(msg or "no Pixel Buds found")
        raise PbctrlError(msg or f"pbpctrl exited with code {proc.returncode}")

    return proc.stdout


# The four ANC modes that participate in the ANC gesture loop.
# NOTE: order matters for `set anc-gesture-loop <off> <active> <aware> [<adaptive>]`.
# The released pbpctrl 0.1.8 (what the AUR ships) only knows `off`/`active`/
# `aware`; the unreleased git HEAD adds `adaptive`.  `detect_anc_modes()` probes
# the installed binary so the GUI exposes exactly the modes it can actually set,
# instead of showing an "Adaptive" button that errors out on 0.1.8.
_ANC_MODES_CACHE: Optional[list[str]] = None


def detect_anc_modes() -> list[str]:
    """Return the ANC modes (off/active/aware[/adaptive]) pbpctrl can set.

    Parses `pbpctrl set anc --help`; the "adaptive" state is present only in
    post-0.1.8 builds.  Falls back to the full superset if the binary can't be
    probed.  The result is cached after the first successful detection.
    """
    global _ANC_MODES_CACHE
    if _ANC_MODES_CACHE is not None:
        return _ANC_MODES_CACHE
    modes: list[str] = list(ANC_STATES)
    try:
        text = _run("set", "anc", "--help", timeout=10.0)
    except PbctrlError:
        pass
    else:
        m = re.search(r"\[possible values:\s*([^\]]*)\]", text)
        if m:
            supported = {v.strip() for v in m.group(1).split(",")}
            detected: list[str] = [s for s in ANC_STATES if s in supported]
            if detected:
                modes = detected
    _ANC_MODES_CACHE = modes
    return modes


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

@dataclass
class BatteryInfo:
    level: Optional[int] = None
    state: Optional[str] = None  # "charging" | "not charging" | "unknown"


@dataclass
class BatteryReport:
    case: Optional[BatteryInfo] = None
    left: Optional[BatteryInfo] = None
    right: Optional[BatteryInfo] = None


@dataclass
class PlacementReport:
    """Whether each bud is detected as seated in the case.

    `None` means the placement is unknown (e.g. buds out of range). The case
    has no Bluetooth radio of its own, so its charge is only relayed through a
    bud that is seated in it -- this tells us whether that relay is possible.
    """

    left_in_case: Optional[bool] = None
    right_in_case: Optional[bool] = None


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

_BAT_LINE = re.compile(r"^(case|left bud|right bud):\s*(.+)$")
_BAT_VAL = re.compile(r"^(\d+)%\s*\(([^)]*)\)$")


def parse_battery(text: str) -> BatteryReport:
    rep = BatteryReport()
    for raw in text.splitlines():
        m = _BAT_LINE.match(raw.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        bm = _BAT_VAL.match(val)
        if bm:
            info: Optional[BatteryInfo] = BatteryInfo(
                level=int(bm.group(1)), state=bm.group(2) or None
            )
        elif val == "unknown":
            info = None
        else:
            # Not a battery line. `show runtime` also emits a `placement:`
            # block whose values are "in case" / "out of case" -- those must
            # not overwrite the battery fields already parsed above.
            continue
        if key == "case":
            rep.case = info
        elif key == "left bud":
            rep.left = info
        elif key == "right bud":
            rep.right = info
    return rep


def parse_anc(text: str) -> str:
    return (text.strip().split() or ["unknown"])[0]


_PLACE_LINE = re.compile(r"^(left bud|right bud):\s*(in case|out of case)$")


def parse_placement(text: str) -> PlacementReport:
    """Parse the ``placement:`` block of `pbpctrl show runtime` output."""
    rep = PlacementReport()
    for raw in text.splitlines():
        m = _PLACE_LINE.match(raw.strip())
        if not m:
            continue
        in_case = m.group(2) == "in case"
        if m.group(1) == "left bud":
            rep.left_in_case = in_case
        else:
            rep.right_in_case = in_case
    return rep


def parse_eq(text: str) -> list[float]:
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    return [float(x) for x in nums[:5]]


def parse_balance(text: str) -> int:
    m = re.search(r"left:\s*(\d+)%,\s*right:\s*(\d+)%", text)
    if not m:
        return 0
    left, right = int(m.group(1)), int(m.group(2))
    if left < 100:      # positive asymmetry: value = 100 - left
        return 100 - left
    if right < 100:     # negative asymmetry: value = right - 100
        return right - 100
    return 0


def parse_gesture_control(text: str) -> tuple[str, str]:
    m = re.search(r"left:\s*(\S+),\s*right:\s*(\S+)", text)
    if not m:
        return ("anc", "anc")
    return m.group(1), m.group(2)


def parse_anc_loop(text: str) -> dict[str, bool]:
    inner = text.strip().strip("[]")
    enabled = {x.strip() for x in inner.split(",") if x.strip()}
    return {m: (m in enabled) for m in ANC_LOOP_MODES}


def parse_keyed(text: str) -> dict[str, str]:
    """Parse simple 'key: value' blocks (show software / show hardware)."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = val.strip()
    return out


# --------------------------------------------------------------------------- #
# High-level operations
# --------------------------------------------------------------------------- #

def get_battery(device: Optional[str] = None) -> BatteryReport:
    return parse_battery(_run("show", "battery", device=device))


def get_placement(device: Optional[str] = None) -> PlacementReport:
    return parse_placement(_run("show", "runtime", device=device))


def get_runtime(device: Optional[str] = None) -> tuple[BatteryReport, PlacementReport]:
    """Fetch battery + placement from a single `pbpctrl show runtime` call.

    `show runtime` reports both the battery info and the per-bud placement in
    one runtime-info event, so a single connection yields a consistent snapshot
    of the two. Using one call instead of `get_battery()` + `get_placement()`
    also halves the number of RFCOMM handshakes -- important because the buds
    hand the maestro connection off between each other and can reset it mid-
    handoff, which occasionally made the two values disagree.
    """
    text = _run("show", "runtime", device=device)
    return parse_battery(text), parse_placement(text)


def get_anc(device: Optional[str] = None) -> str:
    return parse_anc(_run("get", "anc", device=device))


def get_eq(device: Optional[str] = None) -> list[float]:
    return parse_eq(_run("get", "eq", device=device))


def get_balance(device: Optional[str] = None) -> int:
    return parse_balance(_run("get", "balance", device=device))


def get_gesture_control(device: Optional[str] = None) -> tuple[str, str]:
    return parse_gesture_control(_run("get", "gesture-control", device=device))


def get_anc_loop(device: Optional[str] = None) -> dict[str, bool]:
    return parse_anc_loop(_run("get", "anc-gesture-loop", device=device))


def get_bool(name: str, device: Optional[str] = None) -> bool:
    return _run("get", name, device=device).strip().lower() == "true"


def get_firmware(device: Optional[str] = None) -> dict[str, str]:
    """Return {'case': ver, 'left bud': ver, 'right bud': ver}."""
    return parse_keyed(_run("show", "software", device=device))


def get_serials(device: Optional[str] = None) -> dict[str, str]:
    return parse_keyed(_run("show", "hardware", device=device))


# --- setters -------------------------------------------------------------- #

def set_anc(state: str, device: Optional[str] = None) -> None:
    if state not in ANC_STATES:
        raise ValueError(f"invalid ANC state: {state}")
    _run("set", "anc", state, device=device)


def cycle_anc(device: Optional[str] = None) -> None:
    _run("set", "anc", "cycle-next", device=device)


def set_eq(bands, device: Optional[str] = None) -> None:
    if len(bands) != 5:
        raise ValueError("EQ requires exactly 5 bands")
    # pbpctrl's clap parser treats a leading "-" as a flag, so a negative band
    # (e.g. "-3.00") is rejected as "unexpected argument '-3'".  The "--"
    # separator forces every following token to be parsed as a positional
    # value.  It is harmless for non-negative bands, so we always pass it.
    _run("set", "eq", "--", *[f"{float(b):.2f}" for b in bands], device=device)


def set_balance(value: int, device: Optional[str] = None) -> None:
    # Same clap quirk: `pbpctrl set balance -50` fails with "unexpected
    # argument '-5'", which is exactly why the balance slider only worked
    # toward the right.  "--" makes negative (left) values parse correctly.
    _run("set", "balance", "--", str(int(value)), device=device)


def set_bool(name: str, value: bool, device: Optional[str] = None) -> None:
    _run("set", name, "true" if value else "false", device=device)


def set_bool_verified(name: str, value: bool, device: Optional[str] = None) -> None:
    """Set a boolean setting and confirm the buds actually stored it.

    Some settings (multipoint, on-head detection, diagnostics, speech
    detection, volume-exposure notifications) are accepted by the firmware's
    WriteSetting RPC but silently ignored on certain Pixel Buds Pro firmware --
    notably the Pro 2, where pbpctrl's setting support is still incomplete.
    Reading the value back and comparing lets us detect that and surface an
    honest error instead of claiming the toggle worked.
    """
    set_bool(name, value, device=device)
    actual = get_bool(name, device=device)
    if actual != value:
        raise PbctrlError(
            f"firmware did not apply {name!r} (read back {actual!r})"
        )


def set_gesture_control(left: str, right: str, device: Optional[str] = None) -> None:
    if left not in GESTURE_ACTIONS or right not in GESTURE_ACTIONS:
        raise ValueError(f"invalid gesture action: {left}, {right}")
    _run("set", "gesture-control", left, right, device=device)


def set_anc_loop(modes: dict[str, bool], device: Optional[str] = None) -> None:
    # Iterate the dict's own key order (which the GUI builds from the detected
    # mode list) so an older pbpctrl that accepts three modes never receives a
    # fourth `adaptive` argument.  pbpctrl expects:
    #   set anc-gesture-loop <off> <active> <aware> [<adaptive>]
    order = [m for m in modes if m in ANC_LOOP_MODES]
    enabled = [m for m in order if modes.get(m)]
    if len(enabled) < 2:
        raise ValueError("ANC gesture loop requires at least 2 enabled modes")
    args = ["true" if modes.get(m) else "false" for m in order]
    _run("set", "anc-gesture-loop", *args, device=device)
