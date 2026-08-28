#!/usr/bin/env python3
"""
Generate sprites.png + sprites.json from individual asset sources.
Packs: left, case, right, disconnected (from images/).
Sprite sheet is a single row; manifest records {name: {x, y, w, h}}.
"""

import os
import sys
import json
from PIL import Image

_DEFAULT_IMAGES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "../images"))

SOURCES = [
    ("left",         "pixel_bud_left.png"),
    ("case",         "pixel_bud_case.png"),
    ("right",        "pixel_bud_right.png"),
    ("disconnected", "pixel_case_closed.png"),
]


def build_sprites(out_dir: str, src_dir: str = _DEFAULT_IMAGES_DIR):
    images = {}
    for name, fname in SOURCES:
        path = os.path.join(src_dir, fname)
        try:
            images[name] = Image.open(path).convert("RGBA")
        except FileNotFoundError:
            sys.exit(f"gen_sprites: missing source image: {path}")
        except Exception as exc:
            sys.exit(f"gen_sprites: failed to open {path}: {exc}")

    padding = 4
    total_w = sum(img.width for img in images.values()) + padding * (len(images) - 1)
    total_h = max(img.height for img in images.values())

    sheet = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    manifest = {}
    x = 0
    for name, img in images.items():
        y = (total_h - img.height) // 2  # vertically centered
        sheet.paste(img, (x, y))
        manifest[name] = {"x": x, "y": y, "w": img.width, "h": img.height}
        x += img.width + padding

    os.makedirs(out_dir, exist_ok=True)
    sheet.save(os.path.join(out_dir, "sprites.png"))
    with open(os.path.join(out_dir, "sprites.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"gen_sprites.py: sprites.png ({total_w}×{total_h}px), manifest: {manifest}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.local/share/pbwidget")
    src = sys.argv[2] if len(sys.argv) > 2 else _DEFAULT_IMAGES_DIR
    build_sprites(out, src)
