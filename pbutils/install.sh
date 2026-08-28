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
# The Bluetooth MAC is auto-detected from `bluetoothctl devices`; pass it as the
# first argument to override. Non-interactive: set PBPCTRL_MAC in the environment.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SHARE_DIR="$HOME/.local/share/pbwidget"
CONF_PATH="$HOME/.pbwidget"
UNIT_DIR="$HOME/.config/systemd/user"

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
if [[ -z "$MAC" ]] && command -v bluetoothctl >/dev/null 2>&1; then
    MAC="$(bluetoothctl devices 2>/dev/null | grep -i 'pixel buds' | awk '{print $2}' | head -n1 || true)"
fi
if [[ -z "$MAC" ]]; then
    echo "Could not auto-detect your Pixel Buds MAC." >&2
    echo "Run: bluetoothctl devices   then re-run:  ./install.sh AB:CD:EF:01:23:45" >&2
    exit 1
fi
echo "using MAC: $MAC"

# --- install binaries + sprites -------------------------------------------- #
mkdir -p "$BIN_DIR" "$SHARE_DIR" "$UNIT_DIR"
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
sed -e "s|YOUR_MAC_HERE|$MAC|" "$SRC_DIR/systemd/pbwatch.service" > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now pbwatch.service

echo
echo "Done. Status:  systemctl --user status pbwatch"
echo "Widget test:  $BIN_DIR/pbwidget  (writes a PNG next to it)"
echo "Config:       $CONF_PATH"
