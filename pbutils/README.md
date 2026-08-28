# pbutils (vendored)

Vendored from <https://github.com/yom/pbutils> (commit at time of vendoring,
August 2026). `pbwatch` is a background daemon that holds a persistent RFCOMM
connection to Pixel Buds and writes a battery/ANC snapshot to
`$XDG_RUNTIME_DIR/pbwatch/`; `pbwidget` renders that snapshot to a PNG and fires
a `dunst` notification.

> ⚠ **Licensing:** upstream `yom/pbutils` has **no LICENSE file** as of this
> vendoring, which means it defaults to all-rights-reserved. It is kept here as
> a clearly-separated, attributed subdirectory. If you intend to redistribute
> broadly, ask upstream to add a license (or replace with an equivalently
> licensed monitor) first. The surrounding `pixelbuds-gui` project remains MIT.

## Files

| path | what |
|------|------|
| `bin/pbwatch` | the daemon (persistent RFCOMM → state files) — upstream verbatim |
| `bin/pbwidget` | the widget renderer (state files → PNG + dunst) — upstream verbatim |
| `scripts/gen_sprites.py` | packs `images/*.png` into `sprites.png` + `sprites.json` |
| `images/*.png` | source sprites (left/case/right/closed) |
| `systemd/pbwatch.service` | **Arch/CachyOS-adapted** user service (upstream ships a Debian-oriented one) |
| `pbwidget.conf.example` | example widget config (copied to `~/.pbwidget`) |
| `install.sh` | **Arch/CachyOS installer** (upstream ships a Debian `install.sh`) |

## Install (Arch / CachyOS)

```
./install.sh                # auto-detects the Pixel Buds MAC
./install.sh AB:CD:EF:...   # or pass it explicitly
```

This installs deps via `pacman`, the two scripts to `~/.local/bin`, sprites to
`~/.local/share/pbwidget`, a config to `~/.pbwidget`, and enables the
`pbwatch` user service.

## Integration with pixelbuds-gui

The GUI (`pixelbuds_gui/pbwatch_client.py`) reads the daemon's state files when
they're fresh, so it gets battery/placement/ANC **without opening a second RFCOMM
connection** — this avoids the maestro-connection handoff contention between the
two processes. When the daemon isn't running (or its files are stale), the GUI
falls back to a live `pbpctrl` read exactly as before.

Note: settings *writes* (eq, balance, gestures, bools) still go through
`pbpctrl` and open their own RFCOMM connection; while `pbwatch` is connected
those writes occasionally fail and are handled by the GUI's existing error
paths. Reads are unaffected.

## Notes / tuning

- `PBWATCH_FRESH_SECONDS` (default `90`) controls how long a `pbwatch` state
  file is considered live by the GUI. If your buds push battery updates slowly,
  raise it; if you want faster fallback after the daemon stops, lower it.
- The widget's battery/ear icons come from your icon theme's symbolic status
  icons (`adwaita-icon-theme` on Arch); without them the widget still renders,
  just with plain arc gauges.
- `--heal-audio` (WirePlumber auto-routing) is available but not enabled by
  default — add it via `systemctl --user edit pbwatch` if needed.
