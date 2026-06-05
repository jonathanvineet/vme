import cv2
import numpy as np

# ==========================================
# LOAD IMAGE
# ==========================================

IMAGE_PATH = "rebar2.png"

image = cv2.imread(IMAGE_PATH)

if image is None:
    print(f"Could not load {IMAGE_PATH}")
    exit()

display = image.copy()

# ==========================================
# PREPROCESS
# ==========================================

gray = cv2.cvtColor(
    image,
    cv2.COLOR_BGR2GRAY
)

# Normalize contrast

gray = cv2.normalize(
    gray,
    None,
    0,
    255,
    cv2.NORM_MINMAX
)

# CLAHE

clahe = cv2.createCLAHE(
    clipLimit=2.0,
    tileGridSize=(8, 8)
)

gray = clahe.apply(gray)

# Slight blur

gray = cv2.GaussianBlur(
    gray,
    (3, 3),
    0
)

# ==========================================
# LSD DETECTOR
# ==========================================

lsd = cv2.createLineSegmentDetector()

detected = lsd.detect(gray)

if detected[0] is None:
    print("No lines detected")
    exit()

lines = detected[0]

# ==========================================
# COUNTERS
# ==========================================

vertical_count = 0
horizontal_count = 0

# ==========================================
# DRAW DETECTED SEGMENTS
# ==========================================

for line in lines:

    x1, y1, x2, y2 = line[0]

    length = np.sqrt(
        (x2 - x1) ** 2 +
        (y2 - y1) ** 2
    )

    # Don't kill real rebars
    if length < 25:
        continue

    angle = abs(
        np.degrees(
            np.arctan2(
                y2 - y1,
                x2 - x1
            )
        )
    )

    # ----------------------------------
    # VERTICAL REBARS
    # ----------------------------------

    if angle >= 70:

        cv2.line(
            display,
            (int(x1), int(y1)),
            (int(x2), int(y2)),
            (0, 255, 0),
            2
        )

        vertical_count += 1

    # ----------------------------------
    # HORIZONTAL REBARS
    # ----------------------------------

    elif angle <= 20:

        cv2.line(
            display,
            (int(x1), int(y1)),
            (int(x2), int(y2)),
            (255, 255, 0),
            2
        )

        horizontal_count += 1

# ==========================================
# TEXT
# ==========================================

cv2.putText(
    display,
    f"Vertical: {vertical_count}",
    (20, 40),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.8,
    (0, 255, 0),
    2
)

cv2.putText(
    display,
    f"Horizontal: {horizontal_count}",
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
print("Detected Segments")
print("-----------------")
print(f"Vertical   : {vertical_count}")
print(f"Horizontal : {horizontal_count}")
print()

# ==========================================
# SHOW
# ==========================================

cv2.namedWindow(
    "Gray",
    cv2.WINDOW_NORMAL
)

cv2.namedWindow(
    "LSD Rebar Detection",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Gray",
    gray
)

cv2.imshow(
    "LSD Rebar Detection",
    display
)

cv2.waitKey(0)
cv2.destroyAllWindows()