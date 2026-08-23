#!/usr/bin/env bash
# Launcher for the pacman-installed (PKGBUILD) layout: source lives in
# /usr/lib/pixelbuds-gui and runs against the system python3 + pyside6.
export PYTHONPATH="/usr/lib/pixelbuds-gui${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m pixelbuds_gui "$@"
