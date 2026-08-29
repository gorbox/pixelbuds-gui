# pixelbuds-gui

A Qt desktop app to control your **Google Pixel Buds Pro** from Linux — the
settings normally only reachable through the Android phone app.

It drives the [`pbpctrl`](https://github.com/qzed/pbpctrl) CLI, which
implements the reverse-engineered Google "Maestro" + GFPS protocols over
Bluetooth RFCOMM. This project is the GUI on top of that.

![status](https://img.shields.io/badge/status-working-green)

## Features

- **Battery** — left bud, right bud, and case (live, with charging state),
  plus per-bud placement (in case / out of case). The case has no Bluetooth
  radio of its own, so its charge is only readable while at least one bud is
  seated in the case.
- **ANC mode** — Off / Transparency / Noise Cancelling / Adaptive, plus the
  ANC gesture loop (which modes the tap-hold cycles through), and a one-shot
  **Cycle** button (`set anc cycle-next`)
- **Equalizer** — 5-band (low bass / bass / mid / treble / upper treble),
  volume-dependent EQ, and quick presets
- **Audio** — left/right balance, mono toggle
- **Gestures** — enable/disable, and the hold action for each bud (ANC or
  Assistant; these are the only two actions `pbpctrl` accepts)
- **Settings** — multipoint, on-head detection, speech detection
  (auto-transparency), volume-exposure notifications, diagnostics, auto-OTA
- **Low-battery alerts** — desktop notification when a bud or the case drops
  below a configurable threshold (default 20%), with re-arm hysteresis so a
  sitting-low bud doesn't re-notify every poll
- **Info** — firmware versions and serial numbers for the case and both buds

## Requirements

- Linux with a working **Bluetooth adapter** and BlueZ
- Your buds **paired to the PC first** (`bluetoothctl pair <MAC>`)
- Arch / CachyOS (for the provided installer/PKGBUILD; other distros work but
  you install `pbpctrl` and Python deps yourself)

## Install

### Option A — one command (recommended)

```bash
git clone <this repo> pixelbuds-gui
cd pixelbuds-gui
./install.sh
```

Then launch with `pixelbuds-gui`, or search "Pixel Buds Pro" in your app
launcher. The installer sets up `uv`, pulls `pbpctrl` from the AUR, creates the
Python environment, and drops a launcher, `.desktop` entry, and app icon into
`~/.local` (icon installed into the hicolor theme as `pixelbuds-gui`).

### Option B — native Arch package (AUR)

```bash
makepkg -si
```

Depends on the `pbpctrl` and `pyside6` Arch packages. To publish on the AUR,
replace the placeholder `url`/`source` in `PKGBUILD` with your repo and run
`makepkg -g` to generate the real checksum.

## Development

```bash
uv sync                      # create the env + install deps
uv run pixelbuds-gui         # run the app
uv run python tests/smoke.py # run the parser/GUI smoke tests
```

## How it works

- `pixelbuds_gui/pbctrl.py` — subprocess wrapper + parsers around `pbpctrl`
- `pixelbuds_gui/notifications.py` — low-battery detection (Qt-free, with
  threshold/hysteresis logic) + `notify-send` delivery
- `pixelbuds_gui/main_window.py` — the Qt UI (all blocking calls run off the
  GUI thread via a worker pool)

## Limitations

- **Pixel Buds Pro (gen 1) only.** The Pro 2 speaks a different protocol that
  `pbpctrl` does not fully support.
- No firmware updates, Google Assistant, or spatial audio — those are locked
  to Google's own app/services.
- Not affiliated with Google. Google and Pixel Buds are trademarks of Google.
