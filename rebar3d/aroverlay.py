#!/usr/bin/env python3
"""Overlay a reconstructed rebar panel on a live camera view of a surface.

The camera sits on a stand looking down at a table / casting bed. The model
is drawn lying flat on the surface at a chosen drawing scale (1:20 by
default). Two ways to register the surface:

  ArUco mode (accurate)   Put one 4x4_50 marker of known printed size flat on
                          the surface. Its pose gives the surface plane, the
                          mm/px scale AND the camera height, which is shown
                          in the HUD. The model origin tracks the marker.

  Height mode (fallback)  No marker visible: give the stand height
                          (--height 1500 or --height 5ft) and the camera's
                          horizontal field of view (--fov). Assumes the
                          camera points straight down; the overlay is a top
                          view you can drag into place.

The scale is chosen automatically by default: once the surface is
registered (marker or height), the panel is fitted to ~70% of the view and
snapped to the nearest standard drawing scale (1:10, 1:20, 1:25 …). Pass
--scale 20 to force one.

Usage:
    python3 aroverlay.py out/PW-GF-09.json --marker-mm 100
    python3 aroverlay.py out/PW-GF-09.json --height 5ft --fov 60
    python3 aroverlay.py out/PW-GF-09.json --scale 20 --image ../arucograp-1.png

Keys: drag = move overlay · r/e = rotate · [ ] = nudge scale · s = save frame · q = quit
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

DIA_COLORS = {  # BGR, same palette as the viewer
    6: (176, 176, 176), 8: (89, 87, 225), 10: (43, 142, 242), 12: (79, 161, 89),
    16: (161, 122, 175), 20: (167, 121, 78), 25: (95, 117, 156), 32: (194, 119, 227),
}
FEAT_COLORS = {"sleeve": (113, 204, 46), "anchor": (43, 142, 242),
               "loop": (67, 159, 255), "corbel": (176, 163, 154), "embed": (153, 138, 127)}


def list_cameras() -> list[str]:
    """Camera names in system order (matches OpenCV AVFoundation indices)."""
    try:
        out = subprocess.run(["system_profiler", "SPCameraDataType", "-json"],
                             capture_output=True, text=True, timeout=15).stdout
        return [c.get("_name", "?") for c in json.loads(out).get("SPCameraDataType", [])]
    except Exception:
        return []


class FFmpegCamera:
    """Capture from an AVFoundation device selected BY NAME via ffmpeg.

    OpenCV's AVFoundation camera indices don't match any enumeration API
    (system_profiler, discovery sessions and ffmpeg all disagree with it),
    so opening "the Lenovo" by index is a gamble. ffmpeg's avfoundation
    input opens devices by their exact name, which is deterministic.
    Exposes the small subset of the cv2.VideoCapture API the loop uses.
    """

    def __init__(self, name: str, w: int = 1280, h: int = 720, fps: int = 30):
        self.w, self.h = w, h
        self.proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "avfoundation", "-framerate", str(fps),
             "-video_size", f"{w}x{h}", "-pixel_format", "nv12",
             "-i", name, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def isOpened(self) -> bool:
        return self.proc.poll() is None

    def read(self):
        n = self.w * self.h * 3
        buf = self.proc.stdout.read(n)
        if buf is None or len(buf) < n:
            return False, None
        return True, np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3).copy()

    def release(self) -> None:
        self.proc.kill()


def open_camera(spec: str):
    """Index -> cv2.VideoCapture; name -> ffmpeg capture on the matching device."""
    if spec.lstrip("-").isdigit():
        return cv2.VideoCapture(int(spec))
    names = list_cameras()
    match = next((n for n in names if spec.lower() in n.lower()), None)
    if match is None:
        sys.exit(f"camera: no device matching {spec!r} — available: {names or 'unknown'}. "
                 f"Plug it in, or pass --camera <index>/<name>.")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10, check=True)
    except Exception:
        print("camera: ffmpeg not found, falling back to cv2 index 0 — "
              "`brew install ffmpeg` for reliable by-name selection", file=sys.stderr)
        return cv2.VideoCapture(0)
    print(f"camera: using {match!r} via ffmpeg/avfoundation")
    return FFmpegCamera(match)


def parse_height(s: str) -> float:
    """'1500' (mm), '1.5m', '5ft', "4'6" -> mm."""
    s = s.strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|ft|')?", s)
    if not m:
        raise argparse.ArgumentTypeError(f"can't parse height {s!r}")
    v, unit = float(m.group(1)), m.group(2) or "mm"
    return v * {"mm": 1.0, "cm": 10.0, "m": 1000.0, "ft": 304.8, "'": 304.8}[unit]


def load_wireframe(model_path: Path, scale: float):
    """Model JSON -> list of (polyline Nx3 in surface mm, BGR color, thickness px hint).

    The panel lies face-down on the surface: model (x, y) spread on the
    table, model z (through-thickness) points up. Everything divided by the
    drawing scale (1:scale).
    """
    m = json.loads(model_path.read_text())
    s = 1.0 / scale
    segs = []
    for b in m["bars"]:
        pts = np.array([[p[0], p[1], p[2]] for p in b["pts"]], float) * s
        segs.append((pts, DIA_COLORS.get(b["d"], (200, 200, 200)), 1))
    w, h, t = m["width"] * s, m["height"] * s, m["thickness"] * s
    box = np.array([[0, 0, 0], [w, 0, 0], [w, h, 0], [0, h, 0], [0, 0, 0]], float)
    segs.append((box, (140, 120, 100), 2))
    segs.append((box + [0, 0, t], (140, 120, 100), 1))
    for lp in m.get("openings", []):
        loop = np.array([[p[0], p[1], 0] for p in lp] + [[lp[0][0], lp[0][1], 0]], float) * s
        segs.append((loop, (207, 190, 23), 1))
    for f in m.get("features", []):
        col = FEAT_COLORS.get(f["kind"], (200, 200, 200))
        if f["kind"] == "sleeve" and f.get("center"):
            cx, cy, r = f["center"][0] * s, f["center"][1] * s, max(f["r"] * s, 1.5)
            ang = np.linspace(0, 2 * np.pi, 17)
            for z in (0.0, t):
                ring = np.stack([cx + r * np.cos(ang), cy + r * np.sin(ang), np.full_like(ang, z)], axis=1)
                segs.append((ring, col, 2))
        elif f.get("box"):
            x0, y0, z0, x1, y1, z1 = [v * s for v in f["box"]]
            for z in (z0, z1):
                rect = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z], [x0, y0, z]], float)
                segs.append((rect, col, 2))
    return m, segs


# ---------------------------------------------------------------- projection

def camera_matrix(frame_w: int, frame_h: int, hfov_deg: float) -> np.ndarray:
    fx = frame_w / (2 * math.tan(math.radians(hfov_deg) / 2))
    return np.array([[fx, 0, frame_w / 2], [0, fx, frame_h / 2], [0, 0, 1]], float)


class Registration:
    """Maps surface coordinates (mm on the table) to image pixels."""

    def __init__(self, args, frame_shape):
        self.args = args
        self.h, self.w = frame_shape[:2]
        self.K = camera_matrix(self.w, self.h, args.fov)
        self.dist = np.zeros(5)
        self.rvec = None  # surface plane pose (ArUco mode)
        self.tvec = None
        self.cam_height = args.height  # mm, may be replaced by marker estimate
        self.offset = np.array([0.0, 0.0])  # user drag, surface mm
        self.rot = 0.0  # user rotation about surface normal, radians
        self.detector = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
            cv2.aruco.DetectorParameters())

    def update_marker(self, frame) -> bool:
        corners, ids, _ = self.detector.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if ids is None or not len(corners):
            return False
        mm = self.args.marker_mm
        half = mm / 2
        obj = np.array([[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], float)
        # use the marker with the largest image area (most reliable pose)
        best = max(corners, key=lambda c: cv2.contourArea(c[0]))
        ok, rvec, tvec = cv2.solvePnP(obj, best[0].astype(float), self.K, self.dist,
                                      flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            return False
        self.rvec, self.tvec = rvec, tvec
        self.cam_height = float(np.linalg.norm(tvec))
        return True

    def project(self, pts3: np.ndarray) -> np.ndarray | None:
        """Surface-frame mm (x, y on table, z up) -> Nx2 pixel coords."""
        c, s = math.cos(self.rot), math.sin(self.rot)
        p = pts3.copy()
        x, y = p[:, 0].copy(), p[:, 1].copy()
        p[:, 0] = c * x - s * y + self.offset[0]
        p[:, 1] = s * x + c * y + self.offset[1]
        if self.rvec is not None:
            img, _ = cv2.projectPoints(p, self.rvec, self.tvec, self.K, self.dist)
            return img.reshape(-1, 2)
        if not self.cam_height:
            return None
        # nadir assumption: uniform mm/px at the surface; points above the
        # surface (z>0) sit closer to the camera and magnify accordingly
        mmpp = 2 * self.cam_height * math.tan(math.radians(self.args.fov) / 2) / self.w
        depth = np.maximum(self.cam_height - p[:, 2], 1.0)
        u = self.w / 2 + (p[:, 0] - self.mid_x()) / mmpp * (self.cam_height / depth)
        v = self.h / 2 + (p[:, 1] - self.mid_y()) / mmpp * (self.cam_height / depth)
        return np.stack([u, v], axis=1)

    def mid_x(self):
        return getattr(self, "_mx", 0.0)

    def mid_y(self):
        return getattr(self, "_my", 0.0)

    def set_center(self, mx, my):
        self._mx, self._my = mx, my

    def mmpp(self) -> float | None:
        if self.rvec is not None:
            return float(np.linalg.norm(self.tvec)) * 2 * math.tan(math.radians(self.args.fov) / 2) / self.w
        if self.cam_height:
            return 2 * self.cam_height * math.tan(math.radians(self.args.fov) / 2) / self.w
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", type=Path, help="panel JSON from rebar3d (out/<name>.json)")
    ap.add_argument("--scale", default="auto",
                    help="drawing scale 1:N on the surface, or 'auto' (default): "
                         "fit the panel to ~70%% of the camera view and snap to a standard scale")
    ap.add_argument("--height", type=parse_height, default=None,
                    help="camera height above surface, e.g. 1500, 1.5m, 5ft (fallback when no marker)")
    ap.add_argument("--fov", type=float, default=60.0, help="camera horizontal FOV in degrees (default 60)")
    ap.add_argument("--marker-mm", type=float, default=100.0, help="printed ArUco side length in mm")
    ap.add_argument("--camera", default="lenovo",
                    help="camera index or name substring (default: the Lenovo webcam)")
    ap.add_argument("--image", type=Path, default=None, help="run on a still image instead of the camera")
    ap.add_argument("--out", type=Path, default=Path("overlay_shot.png"), help="where 's' saves frames")
    args = ap.parse_args()
    auto_scale = str(args.scale).lower() == "auto"
    args.scale = 20.0 if auto_scale else float(args.scale)

    model, segs = load_wireframe(args.model, args.scale)
    if args.image:
        frame0 = cv2.imread(str(args.image))
        if frame0 is None:
            sys.exit(f"can't read {args.image}")
        cap = None
    else:
        cap = open_camera(str(args.camera))
        if not cap.isOpened():
            sys.exit(f"can't open camera {args.camera!r} (try --camera 0 or --image)")
        ok, frame0 = cap.read()
        if not ok:
            sys.exit("camera gave no frame")

    reg = Registration(args, frame0.shape)
    reg.set_center(model["width"] / args.scale / 2, model["height"] / args.scale / 2)

    STD_SCALES = (1, 2, 2.5, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 200)

    def fit_scale():
        """Smallest standard scale at which the panel fits ~70% of the view."""
        mmpp = reg.mmpp()
        if not mmpp:
            return None
        vis_w, vis_h = reg.w * mmpp, reg.h * mmpp
        raw = max(model["width"] / (0.7 * vis_w), model["height"] / (0.7 * vis_h))
        return next((s for s in STD_SCALES if s >= raw), STD_SCALES[-1])

    fitted = not auto_scale

    win = "rebar overlay"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    dragging = {"on": False, "px": 0, "py": 0}

    def on_mouse(ev, x, y, _flags, _param):
        mmpp = reg.mmpp() or 1.0
        if ev == cv2.EVENT_LBUTTONDOWN:
            dragging.update(on=True, px=x, py=y)
        elif ev == cv2.EVENT_LBUTTONUP:
            dragging["on"] = False
        elif ev == cv2.EVENT_MOUSEMOVE and dragging["on"]:
            reg.offset += np.array([(x - dragging["px"]) * mmpp, (y - dragging["py"]) * mmpp])
            dragging.update(px=x, py=y)

    cv2.setMouseCallback(win, on_mouse)

    marker_seen_at = 0.0
    while True:
        if cap is not None:
            ok, frame = cap.read()
            if not ok:
                break
        else:
            frame = frame0.copy()
        if reg.update_marker(frame):
            marker_seen_at = time.time()
        marker_live = time.time() - marker_seen_at < 1.0 and reg.rvec is not None

        if not fitted:
            s = fit_scale()
            if s is not None:
                if abs(s - args.scale) > 1e-9:
                    args.scale = float(s)
                    model, segs = load_wireframe(args.model, args.scale)
                    reg.set_center(model["width"] / args.scale / 2, model["height"] / args.scale / 2)
                fitted = True

        canvas = frame
        for pts3, color, thick in segs:
            px = reg.project(pts3)
            if px is None:
                continue
            poly = px.astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(canvas, [poly], False, color, thick, cv2.LINE_AA)

        mmpp = reg.mmpp()
        hud = [f"{model['name']}  1:{args.scale:g}" + (" (auto)" if auto_scale and fitted else "")]
        if marker_live:
            hud.append(f"ArUco lock - camera height ~ {reg.cam_height:.0f} mm ({reg.cam_height/304.8:.1f} ft)")
        elif reg.rvec is not None:
            hud.append(f"ArUco (last seen) - height ~ {reg.cam_height:.0f} mm")
        elif reg.cam_height:
            hud.append(f"height mode: {reg.cam_height:.0f} mm ({reg.cam_height/304.8:.1f} ft), fov {args.fov:.0f} deg")
        else:
            hud.append("no marker + no --height: overlay unscaled. Set --height or show a marker")
        if mmpp:
            on_surf = model["width"] / args.scale
            hud.append(f"{mmpp:.2f} mm/px - panel prints {on_surf:.0f} mm wide on surface")
        hud.append("drag: move   r/e: rotate   a: auto-fit scale   [ ]: scale nudge   s: save   q: quit")
        for i, line in enumerate(hud):
            cv2.putText(canvas, line, (12, 26 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(canvas, line, (12, 26 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow(win, canvas)
        key = cv2.waitKey(1 if cap is not None else 30) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("r"):
            reg.rot += math.radians(5)
        elif key == ord("e"):
            reg.rot -= math.radians(5)
        elif key == ord("a"):
            fitted = False  # re-fit from the current registration
        elif key == ord("["):
            args.scale *= 1.05
            auto_scale = False
            model, segs = load_wireframe(args.model, args.scale)
        elif key == ord("]"):
            args.scale /= 1.05
            auto_scale = False
            model, segs = load_wireframe(args.model, args.scale)
        elif key == ord("s"):
            cv2.imwrite(str(args.out), canvas)
            print(f"saved {args.out}")

    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
