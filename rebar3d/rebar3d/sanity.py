"""Automated, deterministic sanity checks on a reconstructed panel.

Every fix in this project so far has come from a human (or an agent)
spotting something implausible in a screenshot or a schedule diff and
manually tracing it back to a root cause -- accurate, but slow, and only
as thorough as whoever happened to look. This module runs a fixed set of
cheap, explainable checks against every panel on every run, so an
implausible reconstruction gets flagged automatically instead of waiting
for someone to notice it in the viewer.

Deliberately NOT a model or a learned classifier: every check here is a
concrete, inspectable rule with a stated reason, in the same spirit as
the rest of this codebase's synthesis passes (evidence first, no
guessing). A flag here is a lead to go trace, not a verdict.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .reconstruct import Bar3D, Panel

# Kinds that legitimately run outside [0, thickness] -- a real dowel or
# vertical link protrudes past the panel face or runs the anchor length
# into an adjacent pour, by design (confirmed repeatedly on PW-01's
# genuine 500mm foundation dowels). Every other kind should stay within
# the panel's own physical thickness, plus a small margin for rounding.
THROUGH_THICKNESS_KINDS = ("face-dowel", "link")
Z_MARGIN = 10.0

# Rough plausible range for total reinforcement weight per m^3 of concrete
# in ordinary precast wall/slab/column elements. Wide on purpose -- this
# is a coarse "is this even in the right ballpark" check, not a code
# calculation; real ratios vary a lot with element type and detailing.
PLAUSIBLE_KG_PER_M3 = (20.0, 400.0)


@dataclass
class SanityFinding:
    severity: str  # "error" | "warn"
    message: str


def _concrete_volume_m3(p: Panel) -> float:
    area = p.width * p.height
    for loop in p.openings:
        xs = [pt[0] for pt in loop]
        ys = [pt[1] for pt in loop]
        # shoelace formula
        a = 0.0
        n = len(loop)
        for i in range(n):
            x0, y0 = loop[i]
            x1, y1 = loop[(i + 1) % n]
            a += x0 * y1 - x1 * y0
        area -= abs(a) / 2
    return max(area, 0.0) * p.thickness / 1e9


def check_z_bounds(p: Panel) -> list[SanityFinding]:
    """Every non-through-thickness bar should sit within [0, thickness]."""
    lo, hi = -Z_MARGIN, p.thickness + Z_MARGIN
    offenders: dict[str, int] = {}
    worst = 0.0
    for b in p.bars:
        if b.kind in THROUGH_THICKNESS_KINDS:
            continue
        zs = [pt[2] for pt in b.points]
        if min(zs) < lo or max(zs) > hi:
            key = f"{b.kind} T{b.diameter}"
            offenders[key] = offenders.get(key, 0) + 1
            worst = max(worst, max(max(zs) - hi, lo - min(zs)))
    if not offenders:
        return []
    detail = ", ".join(f"{k} x{n}" for k, n in sorted(offenders.items()))
    return [SanityFinding(
        "error",
        f"{sum(offenders.values())} bar(s) sit outside the panel's own "
        f"thickness ({p.thickness:.0f}mm, +/-{Z_MARGIN:.0f}mm margin) by up "
        f"to {worst:.0f}mm despite not being a through-thickness kind: "
        f"{detail}. Likely a bad section-view thickness reading feeding "
        f"z_lookup -- check classify_sections' consensus filter.",
    )]


def check_steel_ratio(p: Panel) -> list[SanityFinding]:
    """Total reconstructed steel weight per m^3 of concrete, sanity-ranged."""
    vol = _concrete_volume_m3(p)
    if vol < 0.01:
        return []  # degenerate dims already flagged by check_degenerate
    weight = sum(
        (sum(math.dist(a, b) for a, b in zip(bar.points, bar.points[1:])) / 1000)
        * bar.diameter * bar.diameter / 162
        for bar in p.bars
    )
    ratio = weight / vol
    lo, hi = PLAUSIBLE_KG_PER_M3
    if not (lo <= ratio <= hi):
        return [SanityFinding(
            "warn",
            f"reinforcement ratio {ratio:.0f} kg/m3 is outside the usual "
            f"{lo:.0f}-{hi:.0f} kg/m3 range ({weight:.1f}kg steel / {vol:.2f}m3 "
            f"concrete) -- reconstruction is likely badly incomplete or has "
            f"fabricated bars, not just imprecise",
        )]
    return []


def check_outlier_lengths(p: Panel) -> list[SanityFinding]:
    """A single bar's length should never wildly exceed the panel's own
    diagonal -- a longer bar can only be real if it deliberately runs
    across multiple repeated panels, which this pipeline doesn't model."""
    diag = math.hypot(p.width, p.height, p.thickness)
    cap = 1.5 * diag
    offenders = []
    for b in p.bars:
        length = sum(math.dist(a, c) for a, c in zip(b.points, b.points[1:]))
        if length > cap:
            offenders.append((b.kind, b.diameter, length))
    if not offenders:
        return []
    detail = ", ".join(f"{k} T{d} @{l:.0f}mm" for k, d, l in offenders[:5])
    more = f" (+{len(offenders) - 5} more)" if len(offenders) > 5 else ""
    return [SanityFinding(
        "warn",
        f"{len(offenders)} bar(s) exceed 1.5x the panel's own diagonal "
        f"({diag:.0f}mm) in length: {detail}{more} -- likely a mis-chained "
        f"bar bridging unrelated fragments",
    )]


def check_degenerate(p: Panel) -> list[SanityFinding]:
    findings = []
    if not p.bars:
        findings.append(SanityFinding("error", "zero bars reconstructed"))
    if p.thickness <= 0:
        findings.append(SanityFinding("error", f"thickness is {p.thickness:.1f}mm"))
    if p.width <= 0 or p.height <= 0:
        findings.append(SanityFinding("error", f"panel dims are {p.width:.0f}x{p.height:.0f}mm"))
    return findings


CHECKS = (check_degenerate, check_z_bounds, check_steel_ratio, check_outlier_lengths)


def sanity_check(p: Panel) -> list[SanityFinding]:
    out: list[SanityFinding] = []
    for check in CHECKS:
        out.extend(check(p))
    return out


def format_report(findings: list[SanityFinding]) -> str:
    if not findings:
        return "no issues found"
    lines = []
    for f in findings:
        lines.append(f"[{f.severity.upper()}] {f.message}")
    return "\n".join(lines)
