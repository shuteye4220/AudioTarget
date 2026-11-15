"""python -m audiotarget --config /path/to/audiotarget.toml"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import ConfigError, load


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
    except (ConfigError, OSError) as e:
        print(f"config error: {e}", file=sys.stderr)
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
