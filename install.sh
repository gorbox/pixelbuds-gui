#!/usr/bin/env bash
set -euo pipefail

# pixelbuds-gui — one-command installer for Arch / CachyOS.
# Run from the repo root:  ./install.sh
#
# Installs: uv (Python/project manager), pbpctrl (Bluetooth backend from AUR),
# the app's Python environment, and a launcher + .desktop entry.

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m ! \033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

cd "$(dirname "$0")"
INSTALL_DIR="$(pwd -P)"

# --- 1. uv -----------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    say "installing uv…"
    if command -v pacman >/dev/null 2>&1 && pacman -Si uv >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm uv
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- 2. pbpctrl (Bluetooth backend) ----------------------------------------
if ! command -v pbpctrl >/dev/null 2>&1; then
    say "installing pbpctrl from the AUR…"
    if   command -v paru >/dev/null 2>&1; then paru -S --needed --noconfirm pbpctrl
    elif command -v yay  >/dev/null 2>&1; then yay  -S --needed --noconfirm pbpctrl
    else die "install pbpctrl first (e.g. 'paru -S pbpctrl'), then re-run ./install.sh"
    fi
fi

# --- 3. Python environment -------------------------------------------------
say "creating Python environment…"
uv sync

# --- 4. launcher + desktop entry + icon -------------------------------------
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"

# Install the app icon into the hicolor theme so the launcher shows it
# (resolved by name via the `Icon=` key below).
for size in 16 24 32 48 64 128 256; do
    src="$INSTALL_DIR/packaging/icons/hicolor/${size}x${size}/apps/pixelbuds-gui.png"
    dst="$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dst"
    cp "$src" "$dst/pixelbuds-gui.png"
done
command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

cat > "$HOME/.local/bin/pixelbuds-gui" <<EOF
#!/usr/bin/env bash
exec uv run --project "$INSTALL_DIR" python -m pixelbuds_gui "\$@"
EOF
chmod +x "$HOME/.local/bin/pixelbuds-gui"

cat > "$HOME/.local/share/applications/pixelbuds-gui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Pixel Buds Pro
Comment=Control your Google Pixel Buds Pro
Exec=$HOME/.local/bin/pixelbuds-gui
Icon=pixelbuds-gui
Terminal=false
Categories=Audio;Settings;
EOF
command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

say "done — launch with:  pixelbuds-gui   (or search 'Pixel Buds Pro' in your app launcher)"
warn "Make sure your buds are paired to this PC first:  bluetoothctl pair <MAC>"
