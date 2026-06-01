"""Invoke yt-dlp as a subprocess (same Python env as this package)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_EXTRA_PATH_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PATH", "")
    extras = [d for d in _EXTRA_PATH_DIRS if d not in current and Path(d).is_dir()]
    if extras:
        env["PATH"] = ":".join(extras) + (":" if current else "") + current
    return env


def ytdlp_argv() -> list[str]:
    extra: list[str] = []
    if (bun := shutil.which("bun")) and Path(bun).is_file():
        extra = ["--js-runtimes", f"bun:{bun}", "--remote-components", "ejs:npm"]
    elif deno := shutil.which("deno"):
        extra = ["--js-runtimes", f"deno:{deno}", "--remote-components", "ejs:npm"]
    elif shutil.which("node"):
        extra = ["--js-runtimes", "node", "--remote-components", "ejs:github"]

    extractor_args = "youtube:player-client=default,mweb"
    if po_token := os.environ.get("SUPERSEARCH_YTDLP_PO_TOKEN", "").strip():
        extractor_args += f";po_token=mweb.gvs+{po_token}"
    extra += ["--extractor-args", extractor_args]

    return [sys.executable, "-m", "yt_dlp", *extra]


def ytdlp_extra_argv() -> list[str]:
    out: list[str] = []
    if cookies := os.environ.get("SUPERSEARCH_YTDLP_COOKIES", "").strip():
        path = Path(cookies).expanduser()
        if path.is_file():
            out.extend(["--cookies", str(path.resolve())])
    if os.environ.get("SUPERSEARCH_YTDLP_FORCE_IPV4", "").strip().lower() in _TRUTHY:
        out.append("--force-ipv4")
    return out
