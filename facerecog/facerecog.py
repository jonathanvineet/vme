import cv2
import face_recognition
import numpy as np
import os

# ---------------------------------
# Get absolute path to known_faces
# ---------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")

known_face_encodings = []
known_face_names = []

print("Loading known faces...\n")

# ---------------------------------
# Load every person's images
# ---------------------------------
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
                print(f"   ❌ No face found in {filename}")
                continue

            known_face_encodings.append(encodings[0])
            known_face_names.append(person_name)

            print(f"   ✅ Added {person_name}")

print("\n----------------------------")
print(f"Total faces loaded: {len(known_face_names)}")
print("----------------------------\n")

if len(known_face_encodings) == 0:
    print("No known faces were loaded.")
    quit()

# ---------------------------------
# Open webcam
# ---------------------------------
video_capture = cv2.VideoCapture(1)

if not video_capture.isOpened():
    print("Could not open webcam.")
    quit()

while True:

    ret, frame = video_capture.read()

    if not ret:
        break

    # Resize frame for speed
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # Detect faces
    face_locations = face_recognition.face_locations(rgb_small)

    face_encodings = face_recognition.face_encodings(
        rgb_small,
        face_locations
    )

    # Process every detected face
    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):

        name = "Unknown"

        distances = face_recognition.face_distance(
            known_face_encodings,
            face_encoding
        )

        if len(distances) > 0:

            best_match = np.argmin(distances)

            if distances[best_match] < 0.50:
                name = known_face_names[best_match]

        # Scale back up
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        # Green box
        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            (0, 255, 0),
            2
        )

        # Name background
        cv2.rectangle(
            frame,
            (left, bottom - 35),
            (right, bottom),
            (0, 255, 0),
            cv2.FILLED
        )

        # Name
        cv2.putText(
            frame,
            name,
            (left + 6, bottom - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            2
        )

    cv2.imshow("Face Recognition", frame)

    key = cv2.waitKey(1)

    if key == ord("q"):
        break

video_capture.release()
cv2.destroyAllWindows()