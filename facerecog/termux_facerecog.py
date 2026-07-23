import cv2
import face_recognition
import numpy as np
import os
import subprocess
import time

# ---------------------------------
# Paths
# ---------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
WEB_DIR = os.path.join(BASE_DIR, "web")
CAPTURE_PATH = os.path.join(BASE_DIR, "capture.jpg")
LIVE_PATH = os.path.join(WEB_DIR, "live.jpg")

os.makedirs(WEB_DIR, exist_ok=True)

# Camera id: 0 is usually the back camera, 1 the front camera on Android.
# Check with: termux-camera-info
CAMERA_ID = os.environ.get("FACEREC_CAMERA_ID", "0")

known_face_encodings = []
known_face_names = []

print("Loading known faces...\n")

for person_name in os.listdir(KNOWN_FACES_DIR):

    person_folder = os.path.join(KNOWN_FACES_DIR, person_name)

    if not os.path.isdir(person_folder):
        continue

    for filename in os.listdir(person_folder):

        if filename.lower().endswith((".jpg", ".jpeg", ".png")):

            image_path = os.path.join(person_folder, filename)

            print(f"Loading {image_path}")

            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)

            if len(encodings) == 0:
                print(f"   no face found in {filename}")
                continue

            known_face_encodings.append(encodings[0])
            known_face_names.append(person_name)

            print(f"   added {person_name}")

print("\n----------------------------")
print(f"Total faces loaded: {len(known_face_names)}")
print("----------------------------\n")

if len(known_face_encodings) == 0:
    print("No known faces were loaded.")
    raise SystemExit(1)

# ---------------------------------
# index.html: auto-refreshing viewer, served separately with
#   cd web && python -m http.server 8080
# ---------------------------------
index_html = """<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Face Recognition</title>
<style>
  body { margin:0; background:#000; display:flex; justify-content:center; align-items:center; height:100vh; }
  img { max-width:100%; max-height:100%; }
</style>
</head>
<body>
<img id="live" src="live.jpg">
<script>
setInterval(function () {
  document.getElementById('live').src = 'live.jpg?t=' + Date.now();
}, 1000);
</script>
</body>
</html>
"""
with open(os.path.join(WEB_DIR, "index.html"), "w") as f:
    f.write(index_html)


def capture_frame():
    """Grab one still frame from the phone camera via Termux:API."""
    result = subprocess.run(
        ["termux-camera-photo", "-c", CAMERA_ID, CAPTURE_PATH],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("termux-camera-photo failed:", result.stderr.strip())
        return None
    return cv2.imread(CAPTURE_PATH)


print("Starting capture loop. Ctrl+C to stop.")
print("View the live feed by running (in another Termux session):")
print("  cd web && python -m http.server 8080")
print("then open http://127.0.0.1:8080 in the phone's browser.\n")

while True:

    frame = capture_frame()
    if frame is None:
        time.sleep(1)
        continue

    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_small)
    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):

        name = "Unknown"

        distances = face_recognition.face_distance(known_face_encodings, face_encoding)

        if len(distances) > 0:
            best_match = np.argmin(distances)
            if distances[best_match] < 0.50:
                name = known_face_names[best_match]

        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
        cv2.putText(
            frame, name, (left + 6, bottom - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2
        )

    cv2.imwrite(LIVE_PATH, frame)

    # termux-camera-photo itself takes ~1-2s; this just paces retries.
    time.sleep(0.3)
