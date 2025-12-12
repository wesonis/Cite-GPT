from __future__ import annotations

import argparse
import json
from typing import List, Optional

from .config import get_settings
from .zotero_client import ZoteroClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zva",
        description="Zotero Voice Assistant (zva) — utility commands",
        epilog="Run 'zva run' or 'zva --run' to start the GUI",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Start the GUI (same as 'zva run')",
    )

    search = subparsers.add_parser(
        "search",
        help="Query your Zotero library without the audio layer",
    )
    search.add_argument("--author", help="Author substring to fuzzy match")
    search.add_argument("--title", help="Title substring to fuzzy match")
    search.add_argument("--year", help="Publication year to match exactly")
    search.add_argument("--limit", type=int, default=5, help="Maximum number of rows")
    search.add_argument(
        "--raw",
        action="store_true",
        help="Dump raw JSON records instead of formatted output",
    )

    devices = subparsers.add_parser(
        "audio-devices",
        help="List available audio devices and their indexes",
    )
    # add a small 'run' subcommand for consistency
    subparsers.add_parser("run", help="Start the GUI")

    devices.add_argument(
        "--all",
        action="store_true",
        help="Include devices without input channels",
    )

    return parser


def handle_search(args: argparse.Namespace) -> None:
    if not any((args.author, args.title, args.year)):
        raise SystemExit("Provide at least one of --author, --title, or --year")

    settings = get_settings()
    client = ZoteroClient(settings)
    print(client.describe_target())
    matches = client.search_by_fields(
        author=args.author,
        title=args.title,
        year=args.year,
        limit=args.limit,
    )

    if args.raw:
        print(json.dumps(matches, indent=2))
        return

    if not matches:
        print("No items found.")
        return

    for idx, item in enumerate(matches, start=1):
        data = item.get("data", {})
        title = data.get("title", "Untitled")
        authors = ", ".join(
            filter(
                None,
                [
                    " ".join(
                        part for part in (creator.get("firstName"), creator.get("lastName")) if part
                    )
                    for creator in data.get("creators", [])
                ],
            )
        )
        year = (data.get("date") or "").split("-")[0]
        url = data.get("url", "(no url)")
        print(f"{idx}. {title}")
        if authors:
            print(f"   Authors: {authors}")
        if year:
            print(f"   Year: {year}")
        print(f"   Key: {item.get('key')}\n   URL: {url}\n")


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    should_run_gui = getattr(args, "run", False) or args.command == "run" or args.command is None
    if should_run_gui:
        handle_run(args)
        return

    if args.command == "search":
        handle_search(args)
    elif args.command == "audio-devices":
        handle_audio_devices(args)
    else:
        parser.error(f"Unknown command {args.command}")


def handle_audio_devices(args: argparse.Namespace) -> None:
    try:
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover - optional dependency guard
        raise SystemExit("sounddevice is not installed in this environment") from exc

    devices = sd.query_devices()
    header = "Idx  Name (channels)"
    print(header)
    print("-" * len(header))
    for idx, device in enumerate(devices):
        inputs = device.get("max_input_channels", 0)
        outputs = device.get("max_output_channels", 0)
        if inputs <= 0 and not args.all:
            continue
        role = []
        if inputs > 0:
            role.append(f"in:{inputs}")
        if outputs > 0:
            role.append(f"out:{outputs}")
        role_text = ", ".join(role) or "n/a"
        print(f"[{idx:>2}] {device.get('name', 'Unknown')} ({role_text})")


def handle_run(args: argparse.Namespace) -> None:
    try:
        # import lazily so CLI remains lightweight
        from . import main as app_main

        app_main.main()
    except Exception as exc:  # pragma: no cover - bridge to GUI
        raise SystemExit(f"Failed to start GUI: {exc}") from exc


if __name__ == "__main__":
    main()
