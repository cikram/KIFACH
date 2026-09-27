#!/usr/bin/env python
"""Start KIFACH: one command, one port, Windows / macOS / Linux.

    python run.py                 # serve the built frontend and the API on :8000
    python run.py --build         # build the frontend first, then serve
    python run.py --dev           # backend with reload, for use with `npm run dev`
    python run.py --check         # print configuration and exit

The server refuses to pretend: if the frontend has not been built it says so and
still serves the API, and it prints which provider is active and whether results
will be labelled LIVE, CACHED, or MOCK.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"


def ensure_backend_importable() -> None:
    sys.path.insert(0, str(BACKEND))


def npm_command() -> str | None:
    for candidate in ("npm.cmd", "npm") if os.name == "nt" else ("npm",):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def build_frontend() -> bool:
    npm = npm_command()
    if npm is None:
        print("npm was not found on PATH, so the frontend cannot be built here.")
        return False
    if not (FRONTEND / "node_modules").exists():
        print("Installing frontend dependencies…")
        if subprocess.run([npm, "install"], cwd=FRONTEND).returncode != 0:
            return False
    print("Building the frontend…")
    return subprocess.run([npm, "run", "build"], cwd=FRONTEND).returncode == 0


def describe(settings) -> None:
    provider = settings.resolved_provider()
    cache = settings.resolved_cache_mode()
    label = "MOCK" if provider == "mock" else ("CACHED" if cache == "replay" else "LIVE")
    print("KIFACH configuration")
    print(f"  provider       : {provider} (results labelled {label})")
    if provider != "mock":
        print(f"  model          : {settings.vlm_model}")
    print(f"  cache mode     : {cache}")
    print(f"  data directory : {settings.data_root}")
    print(f"  sampling       : {settings.sample_fps} fps, {settings.frame_size}px long side")
    print(
        f"  windows        : {settings.window_seconds}s with "
        f"{settings.window_overlap}s overlap"
    )
    built = settings.frontend_dist.exists()
    print(f"  frontend build : {'present' if built else 'MISSING (API only)'}")
    if not built:
        print("    Build it with: python run.py --build")


class _DropClientDisconnectNoise(logging.Filter):
    """Windows logs a ConnectionResetError whenever a browser closes an SSE
    stream. It is normal client behaviour, not a server problem, and a demo
    terminal full of tracebacks is worse than useless."""

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        if "_call_connection_lost" in text or "ConnectionResetError" in text:
            return False
        if record.exc_info and record.exc_info[0] is ConnectionResetError:
            return False
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--build", action="store_true", help="build the frontend first")
    parser.add_argument("--dev", action="store_true", help="reload on backend changes")
    parser.add_argument("--check", action="store_true", help="print configuration and exit")
    args = parser.parse_args()

    ensure_backend_importable()
    try:
        import uvicorn
        from app.config import get_settings
    except ImportError as exc:
        print(f"Missing dependency: {exc}.")
        print("Install them with: python -m pip install -r backend/requirements.txt")
        return 1

    settings = get_settings()
    settings.ensure_dirs()

    if args.build and not build_frontend():
        print("The frontend build failed. Fix it, or run with --dev and Vite.")
        return 1

    describe(settings)
    if args.check:
        return 0

    print(f"\n  http://{args.host}:{args.port}   (API docs at /docs)\n")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.dev,
        reload_dirs=[str(BACKEND)] if args.dev else None,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
