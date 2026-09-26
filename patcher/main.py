#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _has_display() -> bool:
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    # headless linux servers/SSH sessions -> no X/Wayland -> use CLI
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _gui_available() -> bool:
    try:
        import webview
    except ImportError:
        return False
    return _has_display()


def main():
    parser = argparse.ArgumentParser(description="openqore modular firmware patcher")
    parser.add_argument("--cli", action="store_true", help="force the text-console interface")
    parser.add_argument("--gui", action="store_true", help="force the graphical interface")
    args = parser.parse_args()

    if args.cli:
        from openqore.core.manager import main as cli_main
        return cli_main()

    if args.gui or _gui_available():
        try:
            from openqore.gui.app import run_gui
            run_gui()
            return 0
        except Exception as e:
            print(f"[warning] GUI failed to start ({e}), falling back to CLI.")

    from openqore.core.manager import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())