"""
Camera-recognition gate. Run one instance per physical gate:

  python3 gate_server.py --mode in  --port 5050
  python3 gate_server.py --mode out --port 5051

Each recognized employee is logged to attendance.xlsx via attendance.py,
debounced per-process so a person standing in frame for several seconds
(recognized every ~400ms) only triggers one write attempt.
"""

import argparse
import base64
import time

import cv2
import face_recognition
import numpy as np
from flask import Flask, jsonify, render_template, request

import attendance
from face_engine import ENGINE

MATCH_TOLERANCE = 0.50
COOLDOWN_SECONDS = 20  # per employee, per process - avoids hammering the xlsx lock

app = Flask(__name__)
GATE_MODE = "in"  # set from argparse in __main__
_last_logged = {}


@app.route("/")
def index():
    return render_template("gate.html", mode=GATE_MODE)


@app.route("/recognize", methods=["POST"])
def recognize():
    ENGINE.maybe_reload()

    data = request.get_json(silent=True) or {}
    image_data_url = data.get("image", "")

    if "," not in image_data_url:
        return jsonify({"faces": []})

    _, encoded = image_data_url.split(",", 1)
    frame_bytes = base64.b64decode(encoded)
    np_arr = np.frombuffer(frame_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"faces": []})

    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_small)
    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    known_encodings, known_employee_ids, known_names = ENGINE.snapshot()

    results = []
    now = time.time()

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        name = "Unknown"
        employee_id = None

        if known_encodings:
            distances = face_recognition.face_distance(known_encodings, face_encoding)
            best_match = int(np.argmin(distances))

            if distances[best_match] < MATCH_TOLERANCE:
                name = known_names[best_match]
                employee_id = known_employee_ids[best_match]

        if employee_id is not None:
            last = _last_logged.get(employee_id, 0)
            if now - last > COOLDOWN_SECONDS:
                _last_logged[employee_id] = now
                attendance.log_event(employee_id, name, GATE_MODE)

        results.append({
            "name": name,
            "top": top * 2,
            "right": right * 2,
            "bottom": bottom * 2,
            "left": left * 2,
        })

    return jsonify({"faces": results})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["in", "out"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    GATE_MODE = args.mode

    app.run(host="0.0.0.0", port=args.port, debug=False, ssl_context="adhoc", threaded=True)
