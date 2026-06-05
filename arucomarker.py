try:
    import cv2
except ModuleNotFoundError as exc:
    raise SystemExit(
        "OpenCV is required. Install it with: python3 -m pip install opencv-contrib-python"
    ) from exc

ARUCO_DICT = cv2.aruco.DICT_4X4_50

image = cv2.imread("arucograp-1.png")

gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
params = cv2.aruco.DetectorParameters()

detector = cv2.aruco.ArucoDetector(
    aruco_dict,
    params
)

corners, ids, _ = detector.detectMarkers(gray)

marker_centers = {}

if ids is not None:

    for marker_corners, marker_id in zip(corners, ids.flatten()):

        pts = marker_corners[0]

        center_x = int(sum(point[0] for point in pts) / len(pts))
        center_y = int(sum(point[1] for point in pts) / len(pts))

        marker_centers[int(marker_id)] = (
            center_x,
            center_y
        )

        cv2.circle(
            image,
            (center_x, center_y),
            5,
            (0, 0, 255),
            -1
        )

        cv2.putText(
            image,
            str(marker_id),
            (center_x + 10, center_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            2
        )

print("\nDetected Marker Centers\n")

for marker_id, center in sorted(marker_centers.items()):
    print(f"ID {marker_id}: {center}")

cv2.imshow("Aruco Graph", image)
cv2.waitKey(0)
cv2.destroyAllWindows()