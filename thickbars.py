import cv2
import numpy as np

# ==========================================
# LOAD IMAGE
# ==========================================

IMAGE_PATH = "rebar2.png"

img = cv2.imread(IMAGE_PATH)

if img is None:
    print("Image not found")
    exit()

display = img.copy()

# ==========================================
# GRAYSCALE
# ==========================================

gray = cv2.cvtColor(
    img,
    cv2.COLOR_BGR2GRAY
)

# ==========================================
# CLAHE
# ==========================================

clahe = cv2.createCLAHE(
    clipLimit=3.0,
    tileGridSize=(8, 8)
)

gray = clahe.apply(gray)

# ==========================================
# BLUR
# ==========================================

gray = cv2.GaussianBlur(
    gray,
    (5, 5),
    0
)

# ==========================================
# EDGE DETECTION
# ==========================================

edges = cv2.Canny(
    gray,
    80,
    180
)

# ==========================================
# LINE DETECTION
# ==========================================

lines = cv2.HoughLinesP(
    edges,
    rho=1,
    theta=np.pi / 180,
    threshold=80,
    minLineLength=120,
    maxLineGap=30
)

bars = []

if lines is not None:

    for line in lines:

        x1, y1, x2, y2 = line[0]

        length = np.sqrt(
            (x2 - x1) ** 2 +
            (y2 - y1) ** 2
        )

        angle = abs(
            np.degrees(
                np.arctan2(
                    y2 - y1,
                    x2 - x1
                )
            )
        )

        # Starter bars are almost vertical

        if not (70 <= angle <= 110):
            continue

        # Must be long

        if length < 150:
            continue

        center_x = int((x1 + x2) / 2)

        bars.append(
            (
                center_x,
                x1,
                y1,
                x2,
                y2,
                length
            )
        )

# ==========================================
# REMOVE DUPLICATES
# ==========================================

bars.sort(
    key=lambda x: x[5],
    reverse=True
)

accepted = []

for bar in bars:

    center_x = bar[0]

    duplicate = False

    for existing in accepted:

        if abs(center_x - existing[0]) < 30:
            duplicate = True
            break

    if not duplicate:
        accepted.append(bar)

# ==========================================
# DRAW
# ==========================================

for idx, bar in enumerate(accepted):

    center_x, x1, y1, x2, y2, length = bar

    cv2.line(
        display,
        (x1, y1),
        (x2, y2),
        (0, 255, 0),
        4
    )

    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)

    cv2.circle(
        display,
        (cx, cy),
        6,
        (0, 0, 255),
        -1
    )

    cv2.putText(
        display,
        f"B{idx+1}",
        (cx + 10, cy),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 0, 0),
        2
    )

# ==========================================
# PRINT RESULTS
# ==========================================

print("\nDetected Starter Bars")
print("---------------------")

for idx, bar in enumerate(accepted):

    print(
        f"Bar {idx+1}: "
        f"Length={bar[5]:.1f}px"
    )

print()
print(
    f"Total Bars: {len(accepted)}"
)

# ==========================================
# SHOW
# ==========================================

cv2.namedWindow(
    "Edges",
    cv2.WINDOW_NORMAL
)

cv2.namedWindow(
    "Starter Bars",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Edges",
    edges
)

cv2.imshow(
    "Starter Bars",
    display
)

cv2.waitKey(0)
cv2.destroyAllWindows()