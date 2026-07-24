"""
Admin console: login + employee enrollment.

  python3 admin_server.py --port 5052

Login uses a simple session password (set ADMIN_PASSWORD env var to
override the default). Enrollment captures >=3 photos per employee
from the browser camera, rejects any photo with zero or multiple
detected faces (bad lighting / wrong framing), then saves the photos
under known_faces/<employee_id>/ and bumps the reload version so the
gate servers pick up the new face without a restart.
"""

import argparse
import base64
import functools
import os
import re

import cv2
import face_recognition
import numpy as np
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import face_engine
from face_engine import ENGINE, KNOWN_FACES_DIR

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
MIN_PHOTOS = 3

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET_KEY", os.urandom(24))


def require_admin(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("dashboard"))
        error = "Wrong password"
    return render_template("admin_login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_admin
def dashboard():
    return render_template("admin_dashboard.html", employees=face_engine.list_employees())


@app.route("/enroll")
@require_admin
def enroll():
    employee_id = request.args.get("employee_id", "")
    name = request.args.get("name", "")
    return render_template(
        "admin_enroll.html",
        employee_id=employee_id,
        name=name,
        min_photos=MIN_PHOTOS,
    )


def _sanitize_employee_id(raw):
    return re.sub(r"[^A-Za-z0-9_-]", "", raw.strip())


@app.route("/enroll/save", methods=["POST"])
@require_admin
def enroll_save():
    data = request.get_json(silent=True) or {}
    employee_id = _sanitize_employee_id(data.get("employee_id", ""))
    name = data.get("name", "").strip()
    images = data.get("images", [])

    if not employee_id or not name:
        return jsonify({"ok": False, "error": "Employee ID and name are required."}), 400

    if len(images) < MIN_PHOTOS:
        return jsonify({"ok": False, "error": f"At least {MIN_PHOTOS} photos are required."}), 400

    decoded_frames = []
    for i, image_data_url in enumerate(images):
        if "," not in image_data_url:
            return jsonify({"ok": False, "error": f"Photo {i + 1} is invalid."}), 400

        _, encoded = image_data_url.split(",", 1)
        frame_bytes = base64.b64decode(encoded)
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"ok": False, "error": f"Photo {i + 1} could not be read."}), 400

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb)

        if len(locations) == 0:
            return jsonify({
                "ok": False,
                "error": f"Photo {i + 1}: no face detected. Retake in better lighting.",
            }), 400

        if len(locations) > 1:
            return jsonify({
                "ok": False,
                "error": f"Photo {i + 1}: multiple faces detected. Only the employee should be in frame.",
            }), 400

        decoded_frames.append(frame)

    folder = os.path.join(KNOWN_FACES_DIR, employee_id)
    os.makedirs(folder, exist_ok=True)

    existing = [f for f in os.listdir(folder) if f.lower().endswith(".jpg")]
    next_index = len(existing) + 1

    for offset, frame in enumerate(decoded_frames):
        path = os.path.join(folder, f"{next_index + offset}.jpg")
        cv2.imwrite(path, frame)

    face_engine.register_employee(employee_id, name)
    face_engine.touch_version()
    ENGINE.reload()

    return jsonify({"ok": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    app.run(host="0.0.0.0", port=args.port, debug=False, ssl_context="adhoc", threaded=True)
