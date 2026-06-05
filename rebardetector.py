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

blur = cv2.GaussianBlur(
    gray,
    (5, 5),
    0
)

# ==========================================
# EDGE DETECTION
# ==========================================

edges = cv2.Canny(
    blur,
    50,
    150
)

# ==========================================
# DETECT LINES
# ==========================================

lines = cv2.HoughLinesP(
    edges,
    rho=1,
    theta=np.pi/180,
    threshold=100,
    minLineLength=100,
    maxLineGap=15
)

# ==========================================
# DRAW REBARS
# ==========================================

count = 0

if lines is not None:

    for line in lines:

        x1, y1, x2, y2 = line[0]

        length = np.sqrt(
            (x2 - x1) ** 2 +
            (y2 - y1) ** 2
        )

        if length < 50:
            continue

        cv2.line(
            display,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        cv2.circle(
            display,
            (x1, y1),
            4,
            (0, 0, 255),
            -1
        )

        cv2.circle(
            display,
            (x2, y2),
            4,
            (255, 0, 0),
            -1
        )

        count += 1

print(f"\nDetected Rebars: {count}")

# ==========================================
# SHOW RESULT
# ==========================================

cv2.namedWindow(
    "Rebar Detection",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Rebar Detection",
    display
)

cv2.waitKey(0)
cv2.destroyAllWindows()