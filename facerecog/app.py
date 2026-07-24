import base64
import os

import cv2
import face_recognition
import numpy as np
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")

app = Flask(__name__)

known_face_encodings = []
known_face_names = []


def load_known_faces():
    print("Loading known faces...\n")

    for person_name in os.listdir(KNOWN_FACES_DIR):
        person_folder = os.path.join(KNOWN_FACES_DIR, person_name)

        if not os.path.isdir(person_folder):
            continue

        for filename in os.listdir(person_folder):
            if filename.lower().endswith((".jpg", ".jpeg", ".png")):
                image_path = os.path.join(person_folder, filename)
                image = face_recognition.load_image_file(image_path)
                encodings = face_recognition.face_encodings(image)

                if len(encodings) == 0:
                    print(f"   no face found in {filename}")
                    continue

                known_face_encodings.append(encodings[0])
                known_face_names.append(person_name)
                print(f"   added {person_name} ({filename})")

    print(f"\nTotal faces loaded: {len(known_face_names)}\n")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/recognize", methods=["POST"])
def recognize():
    data = request.get_json(silent=True) or {}
    image_data_url = data.get("image", "")

    if "," not in image_data_url:
        return jsonify({"faces": []})

    header, encoded = image_data_url.split(",", 1)
    frame_bytes = base64.b64decode(encoded)
    np_arr = np.frombuffer(frame_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"faces": []})

    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_small)
    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    results = []

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        name = "Unknown"

        distances = face_recognition.face_distance(known_face_encodings, face_encoding)

        if len(distances) > 0:
            best_match = np.argmin(distances)
            if distances[best_match] < 0.50:
                name = known_face_names[best_match]

        results.append({
            "name": name,
            # Scale back up to full-size frame coords (we resized by 0.5).
            "top": top * 2,
            "right": right * 2,
            "bottom": bottom * 2,
            "left": left * 2,
        })

    return jsonify({"faces": results})


load_known_faces()

if __name__ == "__main__":
    # host=0.0.0.0 so phones on the same wifi can reach it.
    # adhoc uses a self-signed cert; HTTPS is required for getUserMedia on
    # phone browsers when accessing over a LAN IP (not localhost).
    app.run(host="0.0.0.0", port=5050, debug=False, ssl_context="adhoc")
