#!/usr/bin/env python3
"""Serve the rebar 3D scene editor: an empty world you drag panels into,
resize/rotate/stack them on each other's faces, upload new DWGs on the fly,
and save/load named layouts.

Usage:
    python3 editor.py                 serve on the first free port from 8842
    python3 editor.py --port 9000
    python3 editor.py --no-browser

Ctrl-C to stop.
"""
from __future__ import annotations

import http.server
import json
import re
import socket
import socketserver
import subprocess
import sys
import tempfile
import urllib.parse
import webbrowser
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out"
SCENES = OUT / "scenes"
UPLOADS = OUT / "uploads_src"
TEMPLATE = HERE / "rebar3d" / "editor_template.html"
THREE_JS = HERE / "rebar3d" / "assets_three.js"

SAFE_NAME = re.compile(r"^[A-Za-z0-9._() \-]+$")


def build_editor_html() -> bytes:
    html = TEMPLATE.read_text()
    html = html.replace("__THREE_JS__", THREE_JS.read_text())
    return html.encode("utf-8")


def list_palette() -> list[dict]:
    items = []
    for p in sorted(OUT.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not {"width", "height", "thickness", "name"} <= d.keys():
            continue
        items.append({
            "file": p.name, "name": d["name"],
            "width": d["width"], "height": d["height"], "thickness": d["thickness"],
        })
    return items


def convert_dwg(src: Path) -> dict:
    """Run the existing DWG->3D pipeline on one uploaded drawing, writing its
    JSON straight into OUT so it immediately shows up in the palette."""
    sys.path.insert(0, str(HERE))
    from rebar3d.cli import main as cli_main

    # dwg2dxf refuses to overwrite a stale .dxf from an earlier conversion of
    # a same-named upload ("File not overwritten... use -y") -- clear it first.
    stale_dxf = OUT / "dxf" / f"{src.stem}.dxf"
    stale_dxf.unlink(missing_ok=True)

    before = {p.name for p in OUT.glob("*.json")}
    rc = cli_main([str(src), "-o", str(OUT)])
    if rc:
        raise RuntimeError("pipeline failed")
    after = {p.name for p in OUT.glob("*.json")}
    new = after - before
    if not new:
        # same stem re-uploaded: it overwrote an existing file rather than
        # creating a new one -- report the one matching this upload's stem
        name = src.stem.replace("(R)", "").strip()
        candidate = f"{name}.json"
        if (OUT / candidate).exists():
            new = {candidate}
    if not new:
        raise RuntimeError("conversion produced no panel JSON")
    fname = sorted(new)[0]
    return json.loads((OUT / fname).read_text())


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "RebarEditor/1.0"

    def log_message(self, fmt, *a):
        msg = fmt % a if a else fmt
        print(f"  {msg}")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path in ("/", "/editor.html"):
                self._send_bytes(build_editor_html(), "text/html; charset=utf-8")
            elif path == "/api/palette":
                self._send_json(list_palette())
            elif path.startswith("/api/model/"):
                name = urllib.parse.unquote(path[len("/api/model/"):])
                if not SAFE_NAME.match(name) or "/" in name:
                    return self._send_json({"error": "bad name"}, 400)
                fp = OUT / name
                if not fp.exists():
                    return self._send_json({"error": "not found"}, 404)
                self._send_bytes(fp.read_bytes(), "application/json")
            elif path == "/api/scenes":
                SCENES.mkdir(parents=True, exist_ok=True)
                self._send_json(sorted(p.stem for p in SCENES.glob("*.json")))
            elif path.startswith("/api/scene/"):
                name = urllib.parse.unquote(path[len("/api/scene/"):])
                if not SAFE_NAME.match(name) or "/" in name:
                    return self._send_json({"error": "bad name"}, 400)
                fp = SCENES / f"{name}.json"
                if not fp.exists():
                    return self._send_json({"error": "not found"}, 404)
                self._send_bytes(fp.read_bytes(), "application/json")
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001 - report to the browser, keep server alive
            self._send_json({"error": str(e)}, 500)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            if path == "/api/upload":
                self._handle_upload(body)
            elif path.startswith("/api/scene/"):
                name = urllib.parse.unquote(path[len("/api/scene/"):])
                if not SAFE_NAME.match(name) or "/" in name:
                    return self._send_json({"error": "bad name"}, 400)
                data = json.loads(body)
                SCENES.mkdir(parents=True, exist_ok=True)
                (SCENES / f"{name}.json").write_text(json.dumps(data))
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": str(e)}, 500)

    def _handle_upload(self, body: bytes):
        fname = urllib.parse.unquote(self.headers.get("X-Filename", "upload.dwg"))
        fname = Path(fname).name  # strip any path components
        suffix = Path(fname).suffix.lower()
        if suffix not in (".dwg", ".dxf"):
            return self._send_json({"ok": False, "error": "only .dwg/.dxf accepted"}, 400)
        UPLOADS.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS / fname
        dest.write_bytes(body)
        try:
            model = convert_dwg(dest)
        except Exception as e:  # noqa: BLE001
            return self._send_json({"ok": False, "error": str(e)}, 500)
        self._send_json({"ok": True, "name": model["name"], "file": f"{model['name']}.json"})


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port found")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    SCENES.mkdir(parents=True, exist_ok=True)

    port = args.port or free_port(8842)
    url = f"http://127.0.0.1:{port}/editor.html"
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"rebar3d scene editor: {url}   (Ctrl-C to stop)")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
