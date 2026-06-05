import cv2
import numpy as np

# ==========================================
# LOAD IMAGE
# ==========================================

IMAGE_PATH = "arucograp-1.png"

image = cv2.imread(IMAGE_PATH)

if image is None:
    print(f"Could not load {IMAGE_PATH}")
    exit()

display = image.copy()

# ==========================================
# ARUCO DETECTION
# ==========================================

aruco_dict = cv2.aruco.getPredefinedDictionary(
    cv2.aruco.DICT_4X4_50
)

params = cv2.aruco.DetectorParameters()

detector = cv2.aruco.ArucoDetector(
    aruco_dict,
    params
)

gray = cv2.cvtColor(
    image,
    cv2.COLOR_BGR2GRAY
)

corners, ids, _ = detector.detectMarkers(gray)

if ids is None:
    print("No ArUco markers found.")
    exit()

# ==========================================
# GET CENTERS
# ==========================================

markers = []

for marker_corners, marker_id in zip(
    corners,
    ids.flatten()
):

    pts = marker_corners[0]

    center_x = int(np.mean(pts[:, 0]))
    center_y = int(np.mean(pts[:, 1]))

    markers.append({
        "id": int(marker_id),
        "x": center_x,
        "y": center_y
    })

# ==========================================
# DRAW MARKER CENTERS
# ==========================================

for marker in markers:

    cv2.circle(
        display,
        (marker["x"], marker["y"]),
        6,
        (0, 0, 255),
        -1
    )

    cv2.putText(
        display,
        str(marker["id"]),
        (marker["x"] + 10, marker["y"]),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 0, 0),
        2
    )

# ==========================================
# FIND TOP ROW
# ==========================================

markers_sorted_y = sorted(
    markers,
    key=lambda m: m["y"]
)

# First 6 markers = top row
top_row = markers_sorted_y[:6]

top_row.sort(
    key=lambda m: m["x"]
)

# ==========================================
# FIND LEFT COLUMN
# ==========================================

origin_x = top_row[0]["x"]

left_column = []

for marker in markers:

    if abs(marker["x"] - origin_x) < 60:
        left_column.append(marker)

left_column.sort(
    key=lambda m: m["y"]
)

# ==========================================
# DRAW VERTICAL GRID LINES
# ==========================================

height = display.shape[0]
width = display.shape[1]

for marker in top_row:

    cv2.line(
        display,
        (marker["x"], marker["y"]),
        (marker["x"], height),
        (255, 0, 255),
        2
    )

# ==========================================
# DRAW HORIZONTAL GRID LINES
# ==========================================

for marker in left_column:

    cv2.line(
        display,
        (marker["x"], marker["y"]),
        (width, marker["y"]),
        (255, 0, 255),
        2
    )

# ==========================================
# WORLD COORD LABELS
# ==========================================

for i, marker in enumerate(top_row):

    cv2.putText(
        display,
        f"({i},0)",
        (marker["x"] - 20, marker["y"] - 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 255),
        2
    )

for i, marker in enumerate(left_column):

    cv2.putText(
        display,
        f"(0,{i})",
        (marker["x"] - 45, marker["y"] + 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 255),
        2
    )

# ==========================================
# PRINT MAPPING
# ==========================================

print("\nTOP ROW")

for i, marker in enumerate(top_row):

    print(
        f"Marker {marker['id']} -> "
        f"Pixel({marker['x']},{marker['y']}) -> "
        f"World({i},0)"
    )

print("\nLEFT COLUMN")

for i, marker in enumerate(left_column):

    print(
        f"Marker {marker['id']} -> "
        f"Pixel({marker['x']},{marker['y']}) -> "
        f"World(0,{i})"
    )

# ==========================================
# SHOW RESULT
# ==========================================

cv2.namedWindow(
    "Aruco Graph",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Aruco Graph",
    display
)

cv2.waitKey(0)
cv2.destroyAllWindows()