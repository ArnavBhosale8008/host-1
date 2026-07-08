"""Command-line entry point for DroidPilot."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import Config
from .doctor import format_report, run_checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="droidpilot",
        description="Advanced Android emulator with a built-in local AI assistant.",
    )
    parser.add_argument("--version", action="version", version=f"droidpilot {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("gui", help="Launch the desktop app (default).")
    sub.add_parser("doctor", help="Check the environment (SDK, adb, emulator, Ollama).")
    setup_p = sub.add_parser(
        "setup", help="Download the Android SDK + a Play Store image and create an AVD."
    )
    setup_p.add_argument(
        "--sdk-root", default=None, help="Where to install the SDK (default: platform standard)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.from_env()

    command = args.command or "gui"
    if command == "doctor":
        checks = run_checks(config)
        print(format_report(checks))
        return 0 if all(check.ok for check in checks) else 1

    if command == "setup":
        from pathlib import Path

        from .core.setup import run_setup

        root = Path(args.sdk_root) if args.sdk_root else None
        try:
            run_setup(root)
        except Exception as exc:  # noqa: BLE001 - report and exit non-zero
            print(f"Setup failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # Default: launch the GUI.
    from .gui.app import launch

    return launch(config)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
