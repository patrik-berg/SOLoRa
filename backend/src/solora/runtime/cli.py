"""Shared headless/desktop entry and offline bootstrap recovery CLI."""

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

from filelock import Timeout

from solora.runtime.ownership import owner_lock
from solora.runtime.paths import RuntimePaths
from solora.runtime.settings import ConfigStore, RuntimeConfig
from solora.version import APP_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SOLoRa runtime and offline configuration")
    parser.add_argument("--version", action="version", version=APP_VERSION)
    parser.add_argument("--profile", type=Path)
    for name in ("application", "data", "config", "logs", "runtime"):
        parser.add_argument(f"--{name}", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("server", help="Foreground service; no GUI or browser")
    server.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    commands.add_parser("desktop", help="Open the local control window")
    commands.add_parser("status", help="Show saved configuration and configured URLs")
    configure = commands.add_parser(
        "configure", help="Offline bootstrap recovery; stop the owner first"
    )
    configure.add_argument("--bind")
    configure.add_argument("--port", type=int)
    configure.add_argument("--allow-lan", action="store_true")
    configure.add_argument("--mode", choices=("desktop", "server"))
    args = parser.parse_args(argv)
    paths = RuntimePaths.discover(args.profile)
    paths = replace(
        paths,
        **{
            name: getattr(args, name).resolve()
            for name in ("application", "data", "config", "logs", "runtime")
            if getattr(args, name) is not None
        },
    )
    try:
        paths.prepare()
        store = ConfigStore(paths.config)
        if args.command == "server":
            from solora.runtime.server import serve

            return serve(paths, managed=args.managed)
        if args.command == "desktop":
            from solora.desktop.window import run

            return run(paths)
        if args.command == "configure":
            with owner_lock(paths.data, "desktop"), owner_lock(paths.data, "server"):
                try:
                    previous = store.load()
                except ValueError:
                    print(
                        "Replacing invalid bootstrap config with recovery values.", file=sys.stderr
                    )
                    previous = RuntimeConfig()
                store.save(
                    replace(
                        previous,
                        bind=args.bind if args.bind is not None else previous.bind,
                        port=args.port if args.port is not None else previous.port,
                        lan_confirmed=args.allow_lan or previous.lan_confirmed,
                        mode=args.mode if args.mode is not None else previous.mode,
                    )
                )
        configured = store.load()
        print(
            json.dumps(
                {
                    "app_version": APP_VERSION,
                    "configured": asdict(configured),
                    "configured_urls": configured.urls(),
                    "note": "Configured addresses, not a health assertion. "
                    "Restart the owning app/service to apply.",
                },
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError, Timeout) as error:
        print(f"SOLoRa: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
