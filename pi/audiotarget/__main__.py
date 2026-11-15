"""python -m audiotarget --config /path/to/audiotarget.toml"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import ConfigError, load


def _speak(text: str) -> None:
    """Best effort: on an eyes-free device a silent failure is the worst kind."""
    import subprocess

    try:
        subprocess.run(["espeak-ng", "--", text[:300]], timeout=30, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def main() -> int:
    ap = argparse.ArgumentParser(prog="audiotarget", description=__doc__)
    ap.add_argument("-c", "--config", help="TOML config file")
    ap.add_argument("--dry-run", action="store_true",
                    help="no gun module: print where the target is twice a second")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = load(args.config)
    except (ConfigError, OSError, ValueError) as e:
        print(f"config error: {e}", file=sys.stderr)
        _speak(f"AudioTarget settings error. {e}")
        return 2

    from .app import App

    try:
        asyncio.run(App(cfg, dry_run=args.dry_run, config_path=args.config).run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.getLogger("audiotarget").error("fatal: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
