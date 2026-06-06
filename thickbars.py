import cv2
import numpy as np

# ==========================================
# LOAD IMAGE
# ==========================================

IMAGE_PATH = "rebar.png"

image = cv2.imread(IMAGE_PATH)

if image is None:
    print("Could not load image")
    exit()

display = image.copy()

# ==========================================
# PREPROCESS
# ==========================================

gray = cv2.cvtColor(
    image,
    cv2.COLOR_BGR2GRAY
)

# CLAHE
clahe = cv2.createCLAHE(
    clipLimit=3.0,
    tileGridSize=(8, 8)
)

gray = clahe.apply(gray)

# Bilateral preserves bar edges
gray = cv2.bilateralFilter(
    gray,
    9,
    75,
    75
)

# ==========================================
# LSD DETECTOR
# ==========================================

lsd = cv2.createLineSegmentDetector(0)

result = lsd.detect(gray)

if result[0] is None:
    print("No lines found")
    exit()

lines = result[0]

# ==========================================
# KEEP ONLY LONG VERTICAL SEGMENTS
# ==========================================

vertical_segments = []

for l in lines:

    x1, y1, x2, y2 = l[0]

    dx = x2 - x1
    dy = y2 - y1

    length = np.sqrt(dx * dx + dy * dy)

    if length < 120:
        continue

    angle = abs(
        np.degrees(
            np.arctan2(dy, dx)
        )
    )

    # near vertical
    if 75 <= angle <= 105:

        vertical_segments.append(
            (
                int(x1),
                int(y1),
                int(x2),
                int(y2)
            )
        )

# ==========================================
# MERGE NEARBY LINES
# ==========================================

groups = []

for line in vertical_segments:

    x1, y1, x2, y2 = line

    x_center = (x1 + x2) / 2

    matched = False

    for group in groups:

        if abs(group["x"] - x_center) < 20:

            group["lines"].append(line)

            group["x"] = np.mean([
                (a + c) / 2
                for a, b, c, d
                in group["lines"]
            ])

            matched = True
            break

    if not matched:

        groups.append({
            "x": x_center,
            "lines": [line]
        })

# ==========================================
# BUILD FINAL BARS
# ==========================================

bar_count = 0

for group in groups:

    if len(group["lines"]) < 3:
        continue

    xs = []
    ys = []

    for x1, y1, x2, y2 in group["lines"]:

        xs.extend([x1, x2])
        ys.extend([y1, y2])

    x = int(np.mean(xs))

    y_top = int(min(ys))
    y_bottom = int(max(ys))

    # ignore tiny groups
    if (y_bottom - y_top) < 200:
        continue

    cv2.line(
        display,
        (x, y_top),
        (x, y_bottom),
        (0, 255, 0),
        3
    )

    cv2.putText(
        display,
        f"B{bar_count}",
        (x + 5, y_top + 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 0),
        1
    )

    bar_count += 1

print()
print("Detected Starter Bars:", bar_count)

# ==========================================
# SHOW
# ==========================================

cv2.namedWindow(
    "Starter Bars",
    cv2.WINDOW_NORMAL
)

cv2.imshow(
    "Starter Bars",
    display
)

cv2.waitKey(0)
cv2.destroyAllWindows()