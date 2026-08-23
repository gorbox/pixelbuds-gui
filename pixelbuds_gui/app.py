"""Application entry point."""
from __future__ import annotations

from .main_window import run


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
