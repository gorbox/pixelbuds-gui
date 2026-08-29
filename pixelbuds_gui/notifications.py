"""Low-battery detection + desktop notifications for pixelbuds-gui.

Deliberately small and Qt-free so the threshold/hysteresis logic is unit-
testable without a display. Delivery is a thin, best-effort wrapper around
`notify-send` (the freedesktop notification CLI); it silently no-ops when the
binary is missing or the daemon rejects the message, so a headless or
unconfigured box never crashes the app.

This replaces the removed `pbutils`/`pbwatch` background daemon. The key
difference: that daemon opened its *own* RFCOMM connection and contended with
the GUI for the maestro channel. The GUI already polls `show runtime` every
30s, so the monitor here piggybacks on that existing poll — no extra Bluetooth
traffic, no contention.
"""
from __future__ import annotations

import shutil
import subprocess

DEFAULT_THRESHOLD = 20  # notify at or below this %
HYSTERESIS = 5  # re-arm only after rising back above threshold + this

COMPONENT_LABELS = {"left": "Left bud", "right": "Right bud", "case": "Case"}


class LowBatteryMonitor:
    """Detect components crossing below a charge threshold, with hysteresis.

    Tracks which components have already been notified so the 30s poll loop
    does not re-notify every tick while a bud sits at 5%. A component re-arms
    once it rises back above ``threshold + hysteresis`` (e.g. put on the
    charger). Components read as ``unknown`` are skipped and leave their state
    untouched.
    """

    def __init__(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        hysteresis: int = HYSTERESIS,
    ) -> None:
        self.threshold = threshold
        self.hysteresis = hysteresis
        self._notified: set[str] = set()

    def reset(self) -> None:
        self._notified.clear()

    def check(self, battery) -> list[tuple[str, int]]:
        """Return ``[(component, level), ...]`` for each component that just
        crossed below the threshold. ``battery`` is a ``pbctrl.BatteryReport``.
        """
        crossed: list[tuple[str, int]] = []
        for name in COMPONENT_LABELS:
            info = getattr(battery, name, None)
            if info is None or info.level is None:
                continue
            level = info.level
            if level <= self.threshold:
                if name not in self._notified:
                    self._notified.add(name)
                    crossed.append((name, level))
            elif level >= self.threshold + self.hysteresis:
                self._notified.discard(name)
        return crossed


def send_notification(title: str, body: str, urgency: str = "normal") -> bool:
    """Fire a desktop notification via ``notify-send``. Returns True if sent.

    Best-effort: returns False (rather than raising) when the binary is absent
    or the notification daemon rejects the message.
    """
    binary = shutil.which("notify-send")
    if not binary:
        return False
    try:
        subprocess.run(
            [binary, "-u", urgency, "-a", "pixelbuds-gui", title, body],
            capture_output=True,
            timeout=5.0,
            check=False,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def notify_low_battery(crossed: list[tuple[str, int]]) -> bool:
    """Send one notification covering all components that crossed below."""
    if not crossed:
        return False
    parts = [
        f"{COMPONENT_LABELS.get(name, name)} at {level}%"
        for name, level in crossed
    ]
    return send_notification(
        "Pixel Buds low battery", " · ".join(parts), urgency="critical"
    )
