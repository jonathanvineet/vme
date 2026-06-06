import cv2
import numpy as np

# ==========================================
# CONFIG
# ==========================================

IMAGE_PATH = "rebar.png"

# Change if required
ARUCO_DICT = cv2.aruco.DICT_4X4_50

# ==========================================
# LOAD IMAGE
# ==========================================

image = cv2.imread(IMAGE_PATH)

if image is None:
    print("Could not load image")
    exit()

display = image.copy()

# ==========================================
# DETECT ARUCO
# ==========================================

dictionary = cv2.aruco.getPredefinedDictionary(
    ARUCO_DICT
)

parameters = cv2.aruco.DetectorParameters()

detector = cv2.aruco.ArucoDetector(
    dictionary,
    parameters
)

corners, ids, _ = detector.detectMarkers(
    image
)

if ids is None:

    print("No markers found")
    exit()

ids = ids.flatten()

# ==========================================
# STORE CENTERS
# ==========================================

centers = {}

for marker_corners, marker_id in zip(
    corners,
    ids
):

    pts = marker_corners[0]

    cx = int(np.mean(pts[:, 0]))
    cy = int(np.mean(pts[:, 1]))

    if marker_id not in centers:
        centers[marker_id] = []

    centers[marker_id].append(
        (cx, cy)
    )

# ==========================================
# FIND TOP ROW
# ==========================================

all_points = []

for marker_id in centers:

    for pt in centers[marker_id]:

        all_points.append(
            (
                marker_id,
                pt[0],
                pt[1]
            )
        )

# ==========================================
# TOP ROW
# ==========================================

top_row = sorted(
    all_points,
    key=lambda p: p[1]
)[:6]

top_row = sorted(
    top_row,
    key=lambda p: p[1]
)

# ==========================================
# LEFT COLUMN
# ==========================================

left_column = sorted(
    all_points,
    key=lambda p: p[0]
)[:6]

left_column = sorted(
    left_column,
    key=lambda p: p[2]
)

# ==========================================
# CORNERS
# ==========================================

top_left = np.array([
    top_row[0][1],
    top_row[0][2]
], dtype=np.float32)

top_right = np.array([
    top_row[-1][1],
    top_row[-1][2]
], dtype=np.float32)

bottom_left = np.array([
    left_column[-1][1],
    left_column[-1][2]
], dtype=np.float32)

# Estimate bottom-right

bottom_right = np.array([
    top_right[0] +
    (bottom_left[0] - top_left[0]),

    bottom_left[1]
], dtype=np.float32)

# ==========================================
# SOURCE POINTS
# ==========================================

src = np.array([
    top_left,
    top_right,
    bottom_right,
    bottom_left
], dtype=np.float32)

# ==========================================
# DESTINATION
# ==========================================

WIDTH = 1200
HEIGHT = 1200

dst = np.array([
    [0, 0],
    [WIDTH, 0],
    [WIDTH, HEIGHT],
    [0, HEIGHT]
], dtype=np.float32)

# ==========================================
# HOMOGRAPHY
# ==========================================

H = cv2.getPerspectiveTransform(
    src,
    dst
)

warped = cv2.warpPerspective(
    image,
    H,
    (WIDTH, HEIGHT)
)

# ==========================================
# DRAW DETECTIONS
# ==========================================

for marker_id in centers:

    for (x, y) in centers[marker_id]:

        cv2.circle(
            display,
            (x, y),
            6,
            (0, 255, 0),
            -1
        )

        cv2.putText(
            display,
            str(marker_id),
            (x + 10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2
        )

# ==========================================
# SAVE
# ==========================================

cv2.imwrite(
    "rectified.png",
    warped
)

print()
print("Saved: rectified.png")
print()

# ==========================================
# SHOW
# ==========================================

cv2.namedWindow(
    "Detected Markers",
    cv2.WINDOW_NORMAL
)

cv2.namedWindow(
    "Rectified",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Detected Markers",
    display
)

cv2.imshow(
    "Rectified",
    warped
)

cv2.waitKey(0)
cv2.destroyAllWindows()