"""Super Search CLI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from importlib.metadata import version
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from supersearch.urls import is_youtube_url

_SUBCOMMANDS = frozenset({"search", "cache", "serve"})


def _format_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _youtube_timestamp_url(url: str, start_sec: float) -> str | None:
    if not is_youtube_url(url):
        return None
    p = urlparse(url.strip())
    t = int(start_sec)
    if p.hostname and p.hostname.lower() == "youtu.be":
        base = urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
        return f"{base}?t={t}"
    qs = parse_qs(p.query, keep_blank_values=True)
    qs["t"] = [str(t)]
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(qs, doseq=True), ""))


def _add_search_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", nargs="?", help="YouTube or Twitch video URL")
    parser.add_argument("query", nargs="?", help="Phrase to search for")
    parser.add_argument("-u", "--url", dest="url_flag", metavar="URL")
    parser.add_argument("--query", dest="query_flag", metavar="TEXT")
    parser.add_argument("-n", type=int, default=8, metavar="N")
    parser.add_argument("--whisper", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Ignore cached transcript")
    parser.add_argument("--window-sec", type=float, default=30.0)
    parser.add_argument("--clip-before", type=float, default=3.0)
    parser.add_argument("--clip-after", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")


def _resolve_url_query(args: argparse.Namespace) -> tuple[str, str]:
    url = (args.url_flag or args.url or "").strip()
    query = (args.query_flag or args.query or "").strip()
    if not url:
        raise SystemExit("Error: video URL is required (positional or --url).")
    if not query:
        raise SystemExit("Error: search query is required (positional or --query).")
    return url, query


def _progress_printer(quiet: bool) -> Callable[[dict], None]:
    def on_progress(evt: dict) -> None:
        if quiet:
            return
        phase = evt.get("phase", "")
        if phase in ("error", "result"):
            return
        msg = evt.get("msg") or phase
        if phase in ("downloading", "transcribing"):
            print(
                f"  [{phase}] {evt.get('done', 0)}/{evt.get('total', 0)} — {msg}",
                file=sys.stderr,
            )
        else:
            print(f"  [{phase}] {msg}", file=sys.stderr)

    return on_progress


def cmd_search(args: argparse.Namespace) -> int:
    from supersearch.service import run_super_search

    url, query = _resolve_url_query(args)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    try:
        result = run_super_search(
            url,
            query,
            n=args.n,
            window_sec=args.window_sec,
            clip_extra_before=args.clip_before,
            clip_extra_after=args.clip_after,
            use_whisper=args.whisper,
            force_refresh=args.refresh,
            on_progress=_progress_printer(args.quiet),
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if result.get("warning"):
        print(f"Warning: {result['warning']}", file=sys.stderr)

    hits = result.get("results") or []
    if not hits:
        print("No matches found.")
        return 0

    tags: list[str] = []
    if result.get("cached"):
        tags.append("cached")
    if result.get("whisper_used"):
        tags.append("whisper")
    suffix = f" ({', '.join(tags)})" if tags else ""
    print(f"\nTop {len(hits)} matches for “{query}”{suffix}:\n")

    for i, hit in enumerate(hits, 1):
        start, end = hit["start"], hit["end"]
        line = (
            f"{i}. {_format_time(start)} – {_format_time(end)}  (score {hit.get('score', 0):.2f})"
        )
        if link := _youtube_timestamp_url(url, start):
            line += f"\n   {link}"
        print(line)
        print(f"   {hit.get('context') or hit.get('text', '')[:160]}\n")
    return 0


def cmd_cache_clear(args: argparse.Namespace) -> int:
    from supersearch import cache

    url = (args.url or "").strip()
    if not url:
        print("Error: URL is required.", file=sys.stderr)
        return 1
    if cache.clear(url):
        print(f"Cleared transcript cache for:\n  {url}")
        return 0
    print(f"No cached transcript for:\n  {url}")
    return 0


def cmd_cache_list(_args: argparse.Namespace) -> int:
    from supersearch.cache import cache_dir, list_cached

    rows = list_cached()
    if not rows:
        print("Cache is empty.")
        return 0
    print(f"Transcript cache ({cache_dir()}):\n")
    for row in rows:
        ts = row["fetched_at"]
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"
        print(f"  {when}  [{row['source']}]  {row['entry_count']} entries")
        print(f"    {row['url']}\n")
    return 0


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "supersearch.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="supersearch",
        description="Search YouTube and Twitch VODs by transcript.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  supersearch "https://youtu.be/VIDEO" "funny moment"
  supersearch search -u URL --query "boss fight" --whisper
  supersearch cache list
  supersearch cache clear -u URL
  supersearch serve --port 8000
""",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('supersearch')}")

    sub = parser.add_subparsers(dest="command", metavar="command")

    search_parser = sub.add_parser("search", help="Search a VOD (default)")
    _add_search_flags(search_parser)
    search_parser.set_defaults(func=cmd_search)

    cache_parser = sub.add_parser("cache", help="Transcript cache")
    cache_sub = cache_parser.add_subparsers(dest="cache_cmd", metavar="action", required=True)
    cache_sub.add_parser("list", help="List cached transcripts").set_defaults(func=cmd_cache_list)
    clear_parser = cache_sub.add_parser("clear", help="Drop cache for a URL")
    clear_parser.add_argument("--url", "-u", required=True, metavar="URL")
    clear_parser.set_defaults(func=cmd_cache_clear)

    serve_parser = sub.add_parser("serve", help="Start HTTP API")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv or argv[0] in _SUBCOMMANDS or argv[0].startswith("-"):
        return argv
    if len(argv) >= 2 and not argv[1].startswith("-"):
        return ["search", *argv]
    return argv


def main(argv: list[str] | None = None) -> None:
    raw = list(argv) if argv is not None else sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(_normalize_argv(raw))

    if args.command == "cache":
        if not getattr(args, "cache_cmd", None):
            parser.parse_args([*_normalize_argv(raw), "cache", "-h"])
        sys.exit(args.func(args))

    if args.command == "serve":
        args.func(args)
        return

    if args.command != "search":
        parser.print_help()
        sys.exit(0)

    sys.exit(cmd_search(args))


if __name__ == "__main__":
    main()
