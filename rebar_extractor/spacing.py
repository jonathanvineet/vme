"""
===========================================================
spacing.py

Calculates spacing (gap) between neighbouring rebars.

The spacing is measured perpendicular to the bar direction.

===========================================================
"""

from math import cos, radians, sin


class SpacingCalculator:

    def __init__(self):

        self.angle_tolerance = 10.0

    # -----------------------------------------------------

    def compute(self, rebars):

        if len(rebars) <= 1:
            return rebars

        # Group rebars by orientation
        horizontal = []
        vertical = []
        diagonal = []

        for rb in rebars:

            if rb.orientation == "Horizontal":
                horizontal.append(rb)

            elif rb.orientation == "Vertical":
                vertical.append(rb)

            else:
                diagonal.append(rb)

        self.compute_horizontal(horizontal)
        self.compute_vertical(vertical)
        self.compute_diagonal(diagonal)

        return rebars

    # -----------------------------------------------------

    def compute_horizontal(self, rebars):

        if len(rebars) < 2:
            return

        # Sort by Y coordinate
        rebars.sort(key=lambda r: r.center[1])

        for i in range(len(rebars) - 1):

            gap = abs(

                rebars[i + 1].center[1] -

                rebars[i].center[1]

            )

            rebars[i].spacing = round(gap, 2)

        rebars[-1].spacing = None

    # -----------------------------------------------------

    def compute_vertical(self, rebars):

        if len(rebars) < 2:
            return

        # Sort by X coordinate
        rebars.sort(key=lambda r: r.center[0])

        for i in range(len(rebars) - 1):

            gap = abs(

                rebars[i + 1].center[0] -

                rebars[i].center[0]

            )

            rebars[i].spacing = round(gap, 2)

        rebars[-1].spacing = None

    # -----------------------------------------------------

    def compute_diagonal(self, rebars):

        if len(rebars) < 2:
            return

        # Use projection onto the normal of the bar direction

        rebars.sort(

            key=lambda r: self.project(r)

        )

        for i in range(len(rebars) - 1):

            p1 = self.project(rebars[i])

            p2 = self.project(rebars[i + 1])

            rebars[i].spacing = round(

                abs(p2 - p1),

                2

            )

        rebars[-1].spacing = None

    # -----------------------------------------------------

    def project(self, rb):

        angle = radians(rb.angle + 90)

        nx = cos(angle)
        ny = sin(angle)

        x = rb.center[0]
        y = rb.center[1]

        return x * nx + y * ny