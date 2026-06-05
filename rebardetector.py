import cv2
import numpy as np

# ==========================================
# CONFIG
# ==========================================

IMAGE_PATH = "rebar.png"

MIN_SEGMENT_LENGTH = 25

VERTICAL_ANGLE = 70
HORIZONTAL_ANGLE = 20

CLUSTER_DISTANCE = 8

# ==========================================
# LOAD IMAGE
# ==========================================

image = cv2.imread(IMAGE_PATH)

if image is None:
    print("Could not load image")
    exit()

display = image.copy()

height, width = image.shape[:2]

# ==========================================
# PREPROCESS
# ==========================================

gray = cv2.cvtColor(
    image,
    cv2.COLOR_BGR2GRAY
)

gray = cv2.normalize(
    gray,
    None,
    0,
    255,
    cv2.NORM_MINMAX
)

clahe = cv2.createCLAHE(
    clipLimit=2.0,
    tileGridSize=(8, 8)
)

gray = clahe.apply(gray)

gray = cv2.GaussianBlur(
    gray,
    (3, 3),
    0
)

# ==========================================
# LSD
# ==========================================

lsd = cv2.createLineSegmentDetector()

result = lsd.detect(gray)

if result[0] is None:
    print("No lines found")
    exit()

lines = result[0]

# ==========================================
# STORE SEGMENTS
# ==========================================

vertical_segments = []
horizontal_segments = []

for line in lines:

    x1, y1, x2, y2 = line[0]

    length = np.sqrt(
        (x2 - x1) ** 2 +
        (y2 - y1) ** 2
    )

    if length < MIN_SEGMENT_LENGTH:
        continue

    angle = abs(
        np.degrees(
            np.arctan2(
                y2 - y1,
                x2 - x1
            )
        )
    )

    # --------------------------
    # VERTICAL
    # --------------------------

    if angle >= VERTICAL_ANGLE:

        center_x = int(
            (x1 + x2) / 2
        )

        vertical_segments.append(
            (
                center_x,
                min(y1, y2),
                max(y1, y2)
            )
        )

    # --------------------------
    # HORIZONTAL
    # --------------------------

    elif angle <= HORIZONTAL_ANGLE:

        center_y = int(
            (y1 + y2) / 2
        )

        horizontal_segments.append(
            (
                center_y,
                min(x1, x2),
                max(x1, x2)
            )
        )

# ==========================================
# CLUSTER FUNCTION
# ==========================================

def cluster(values):

    if len(values) == 0:
        return []

    values.sort(key=lambda x: x[0])

    groups = []

    current = [values[0]]

    for item in values[1:]:

        if abs(
            item[0] - current[-1][0]
        ) <= CLUSTER_DISTANCE:

            current.append(item)

        else:

            groups.append(current)
            current = [item]

    groups.append(current)

    return groups

# ==========================================
# MERGE VERTICALS
# ==========================================

vertical_groups = cluster(
    vertical_segments
)

merged_verticals = []

for group in vertical_groups:

    xs = [g[0] for g in group]

    ys1 = [g[1] for g in group]
    ys2 = [g[2] for g in group]

    merged_verticals.append(
        (
            int(np.mean(xs)),
            int(min(ys1)),
            int(max(ys2))
        )
    )

# ==========================================
# MERGE HORIZONTALS
# ==========================================

horizontal_groups = cluster(
    horizontal_segments
)

merged_horizontals = []

for group in horizontal_groups:

    ys = [g[0] for g in group]

    xs1 = [g[1] for g in group]
    xs2 = [g[2] for g in group]

    merged_horizontals.append(
        (
            int(np.mean(ys)),
            int(min(xs1)),
            int(max(xs2))
        )
    )

# ==========================================
# DRAW RECONSTRUCTED REBARS
# ==========================================

for x, y1, y2 in merged_verticals:

    cv2.line(
        display,
        (x, y1),
        (x, y2),
        (0, 255, 0),
        3
    )

for y, x1, x2 in merged_horizontals:

    cv2.line(
        display,
        (x1, y),
        (x2, y),
        (255, 255, 0),
        3
    )

# ==========================================
# TEXT
# ==========================================

cv2.putText(
    display,
    f"Vertical Rebars: {len(merged_verticals)}",
    (20, 40),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.8,
    (0, 255, 0),
    2
)

cv2.putText(
    display,
    f"Horizontal Rebars: {len(merged_horizontals)}",
    (20, 80),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.8,
    (255, 255, 0),
    2
)

# ==========================================
# PRINT
# ==========================================

print()
print("MERGED REBARS")
print("---------------------")
print("Vertical :", len(merged_verticals))
print("Horizontal :", len(merged_horizontals))
print()

# ==========================================
# SHOW
# ==========================================

cv2.namedWindow(
    "Merged Rebars",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Merged Rebars",
    display
)

cv2.waitKey(0)
cv2.destroyAllWindows()