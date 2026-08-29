#!/usr/bin/env bash
# Arch / CachyOS installer for pbutils (pbwatch + pbwidget).
#
#   ./install.sh [MAC]
#
# Installs:
#   - pacman deps (dunst, python-cairo, python-gobject, python-pillow,
#     python-dbus, librsvg; adwaita-icon-theme for battery/ear icons)
#   - pbwatch + pbwidget to ~/.local/bin
#   - sprite sheet to ~/.local/share/pbwidget
#   - example config to ~/.pbwidget (if not present)
#   - systemd user service ~/.config/systemd/user/pbwatch.service
#
# The Bluetooth MAC is resolved in this order:
#   1. first CLI argument
#   2. $PBPCTRL_MAC environment variable
#   3. a previously saved MAC (~/.config/pbwatch/mac)
#   4. auto-detected from `bluetoothctl devices` (Pixel Buds)
#
# If no MAC can be found the install STILL completes — deps, binaries, sprites,
# config and the service unit are all laid down, but the unit is left disabled
# (so it won't try to run against a bogus MAC). Supply a MAC later and re-run;
# it picks up from where it left off (deps + files are idempotent).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SHARE_DIR="$HOME/.local/share/pbwidget"
CONF_PATH="$HOME/.pbwidget"
UNIT_DIR="$HOME/.config/systemd/user"
MAC_FILE="$HOME/.config/pbwatch/mac"

# --- dependencies (idempotent) --------------------------------------------- #
DEPS=(dunst python-cairo python-gobject python-pillow python-dbus librsvg adwaita-icon-theme)
MISSING=()
for d in "${DEPS[@]}"; do
    pacman -Q "$d" >/dev/null 2>&1 || MISSING+=("$d")
done
if ((${#MISSING[@]})); then
    echo "installing missing deps: ${MISSING[*]}"
    sudo pacman -S --needed --noconfirm "${MISSING[@]}"
else
    echo "all deps present"
fi

# --- MAC -------------------------------------------------------------------- #
MAC="${1:-${PBPCTRL_MAC:-}}"
if [[ -z "$MAC" && -f "$MAC_FILE" ]]; then
    MAC="$(cat "$MAC_FILE")"
    echo "using previously saved MAC: $MAC"
fi
if [[ -z "$MAC" ]] && command -v bluetoothctl >/dev/null 2>&1; then
    MAC="$(bluetoothctl devices 2>/dev/null | grep -i 'pixel buds' | awk '{print $2}' | head -n1 || true)"
fi

# --- install binaries + sprites (always) ------------------------------------ #
mkdir -p "$BIN_DIR" "$SHARE_DIR" "$UNIT_DIR" "$(dirname "$MAC_FILE")"
install -m755 "$SRC_DIR/bin/pbwatch"  "$BIN_DIR/pbwatch"
install -m755 "$SRC_DIR/bin/pbwidget" "$BIN_DIR/pbwidget"
python3 "$SRC_DIR/scripts/gen_sprites.py" "$SHARE_DIR" "$SRC_DIR/images"

# --- example config (don't clobber an existing one) ------------------------ #
if [[ ! -f "$CONF_PATH" ]]; then
    cp "$SRC_DIR/pbwidget.conf.example" "$CONF_PATH"
    echo "wrote example config: $CONF_PATH"
else
    echo "config already exists, leaving $CONF_PATH untouched"
fi

# --- systemd user service --------------------------------------------------- #
UNIT="$UNIT_DIR/pbwatch.service"
if [[ -n "$MAC" ]]; then
    sed -e "s|YOUR_MAC_HERE|$MAC|" "$SRC_DIR/systemd/pbwatch.service" > "$UNIT"
    echo "$MAC" > "$MAC_FILE"
    systemctl --user daemon-reload
    systemctl --user enable --now pbwatch.service
else
    # No MAC yet (e.g. buds not paired, or a machine with no BT adapter).
    # Lay the unit down but leave it disabled so it can't run against a bogus
    # MAC; the user finishes wiring the real MAC below.
    cp "$SRC_DIR/systemd/pbwatch.service" "$UNIT"
    systemctl --user daemon-reload
fi

echo
echo "Done."
if [[ -n "$MAC" ]]; then
    echo "Monitor:   systemctl --user status pbwatch  (MAC $MAC)"
else
    echo "⚠ No Pixel Buds MAC found, so pbwatch was installed but NOT enabled."
    echo "  Once your buds are paired (or visible via 'bluetoothctl devices'),"
    echo "  finish with either:"
    echo "    ./install.sh AB:CD:EF:01:23:45"
    echo "  or edit the MAC into $UNIT and run:"
    echo "    systemctl --user enable --now pbwatch"
fi
echo "Widget test:  $BIN_DIR/pbwidget  (writes a PNG next to it)"
echo "Config:       $CONF_PATH"
