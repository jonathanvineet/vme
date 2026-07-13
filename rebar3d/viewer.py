#!/usr/bin/env python3
"""Serve the rebar 3D viewer locally.

Usage:
    python3 viewer.py                 serve existing out/viewer.html
    python3 viewer.py --rebuild      re-run the pipeline on ../DRAWINGS first
    python3 viewer.py --port 9000    pick a port (default: first free from 8742)

Opens the browser automatically. Ctrl-C to stop.
"""
from __future__ import annotations

import argparse
import http.server
import socket
import socketserver
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out"
DRAWINGS = HERE.parent / "DRAWINGS"


def rebuild() -> None:
    sys.path.insert(0, str(HERE))
    from rebar3d.cli import main

    drawings = sorted(DRAWINGS.glob("*(R).dwg"))
    if not drawings:
        sys.exit(f"no (R) reinforcement DWGs found in {DRAWINGS}")
    main([str(p) for p in drawings] + ["-o", str(OUT)])


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port found")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true", help="re-run the DWG pipeline first")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if args.rebuild or not (OUT / "viewer.html").exists():
        rebuild()

    port = args.port or free_port(8742)
    url = f"http://127.0.0.1:{port}/viewer.html"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(OUT), **kw)

        def log_message(self, fmt, *a):  # quieter log: one line per page load
            msg = fmt % a if a else fmt
            if ".html" in msg:
                print(f"  {msg}")

    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"rebar3d viewer: {url}   (Ctrl-C to stop)")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
